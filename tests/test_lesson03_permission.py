"""第 3 课离线测试：三道闸——死名单、规则匹配、用户确认。"""

import types

from fakes import FakeClient, text_response, tool_response
from mini_claude import permission, tools
from mini_claude.loop import agent_loop


# ---------- 第一道闸：死名单 ----------

def test_deny_list_hits():
    reason = permission.check_deny_list("sudo rm -rf /")
    assert "rm -rf /" in reason  # 名单里它排在 sudo 前面，先命中先报
    assert permission.check_deny_list("echo hello") is None


def test_deny_list_blocks_before_execution():
    """死名单拦截根本不会调用 ask_user——没得商量。"""
    class FakeBlock:
        name = "bash"
        input = {"command": "sudo ls"}

    assert permission.check_permission(FakeBlock()) is False


# ---------- 第二道闸：规则匹配 ----------

def test_destructive_command_word_regex():
    """rm 必须作为命令词出现才算数；firm、echo rm 这种无辜串不误伤。"""
    assert permission.contains_destructive_command("rm old.txt")
    assert permission.contains_destructive_command("ls; rm old.txt")
    assert not permission.contains_destructive_command("echo firm")
    assert not permission.contains_destructive_command("echo rm")


def test_rule_file_outside_workspace(tmp_path, monkeypatch):
    """读写编辑工具的路径越界 -> 命中规则（不问死名单）。"""
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    msg = permission.check_rules("write_file", {"path": "../x.txt", "content": "hi"})
    assert msg == "Writing outside workspace"
    assert permission.check_rules("write_file", {"path": "in.txt", "content": "hi"}) is None


def test_rule_destructive_bash():
    assert permission.check_rules("bash", {"command": "rm old.txt"}) == "Potentially destructive command"
    assert permission.check_rules("bash", {"command": "echo hi"}) is None


# ---------- 第三道闸：用户确认 ----------

def test_ask_user_allow(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    assert permission.ask_user("bash", {"command": "rm x"}, "测试") == "allow"


def test_ask_user_deny_by_default(monkeypatch):
    """直接回车 = 不允许：默认答案必须是安全的那一个。"""
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert permission.ask_user("bash", {"command": "rm x"}, "测试") == "deny"


def test_check_permission_ask_flow(monkeypatch):
    """可疑操作走到第三道闸：用户点头放行，摇头拦下。"""
    block = types.SimpleNamespace(name="bash", input={"command": "rm old.txt"})
    monkeypatch.setattr(permission, "ask_user", lambda *a: "allow")
    assert permission.check_permission(block) is True
    monkeypatch.setattr(permission, "ask_user", lambda *a: "deny")
    assert permission.check_permission(block) is False


# ---------- 在循环里 ----------

def test_loop_denied_command_not_executed(tmp_path, monkeypatch):
    """rm 命令被第三道闸拦下：文件安然无恙，模型收到拒绝话术。"""
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    (tmp_path / "old.txt").write_text("珍贵数据")
    monkeypatch.setattr(permission, "ask_user", lambda *a: "deny")

    client = FakeClient([
        tool_response("bash", {"command": "rm old.txt"}),
        text_response("您拒绝了，那我不删了。"),
    ])
    messages = [{"role": "user", "content": "删掉 old.txt"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "Permission denied."
    assert (tmp_path / "old.txt").read_text() == "珍贵数据"  # 命令没有真的执行


def test_loop_allows_safe_command(tmp_path, monkeypatch):
    """安全命令一路绿灯：三道闸不该挡正常工作。"""
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    client = FakeClient([
        tool_response("bash", {"command": "echo fine"}),
        text_response("输出是 fine"),
    ])
    messages = [{"role": "user", "content": "跑 echo"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "fine"
