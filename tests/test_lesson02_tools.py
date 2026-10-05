"""第 2 课离线测试：五件套工具 + 分发表 + 一次多张调用单。"""

from types import SimpleNamespace

from fakes import FakeClient, text_response, tool_block, tool_response
from mini_claude.loop import agent_loop
from mini_claude import tools


# ---------- 工具函数本身 ----------

def test_write_read_roundtrip(tmp_path, monkeypatch):
    """写进去、读出来，内容一致。"""
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    assert tools.run_write("notes/a.txt", "hello") == "Wrote 5 bytes to notes/a.txt"
    assert tools.run_read("notes/a.txt") == "hello"


def test_read_limit_truncates(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    tmp_path.joinpath("big.txt").write_text("\n".join(f"L{i}" for i in range(1, 6)))
    out = tools.run_read("big.txt", limit=2)
    assert out.splitlines() == ["L1", "L2", "... (3 more lines)"]


def test_edit_replaces_only_first(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    tools.run_write("f.txt", "a a a")
    tools.run_edit("f.txt", "a", "b")
    assert tools.run_read("f.txt") == "b a a"


def test_edit_missing_text_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    tools.run_write("f.txt", "hello")
    assert tools.run_edit("f.txt", "不存在的字", "x") == "Error: text not found in f.txt"


def test_path_outside_workspace_rejected(tmp_path, monkeypatch):
    """safe_path 是文件工具的安全边界：越界路径直接报错，不写盘。"""
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    out = tools.run_write("../evil.txt", "hack")
    assert out.startswith("Error: Path escapes workspace")
    assert not (tmp_path.parent / "evil.txt").exists()


def test_glob_recursive_and_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKDIR", tmp_path)
    tools.run_write("src/a.txt", "x")
    tools.run_write("src/deep/b.txt", "x")
    assert tools.run_glob("**/*.txt").splitlines() == ["src/a.txt", "src/deep/b.txt"]
    assert tools.run_glob("*.md") == "(no matches)"


# ---------- 分发表与循环 ----------

def test_one_response_many_tool_calls():
    """一次回复夹两张单子：bash + glob 并行，回填时各配各的 tool_use_id。"""
    two_calls = SimpleNamespace(content=[
        tool_block("bash", {"command": "echo hi-agent"}, "tool-1"),
        tool_block("glob", {"pattern": "mini_claude/*.py"}, "tool-2"),
    ])
    client = FakeClient([two_calls, text_response("找到了，loop.py 一共 87 行。")])
    messages = [{"role": "user", "content": "看看有哪些 py 文件，loop.py 多少行"}]

    agent_loop(messages, client, "fake-model")

    results = messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["tool-1", "tool-2"]
    assert results[0]["content"] == "hi-agent"                    # bash 真执行了
    assert "mini_claude/loop.py" in results[1]["content"]         # glob 真匹配到了


def test_unknown_tool_returns_error_to_model():
    """模型点了不存在的工具：不崩，把错误话术交回让它自己纠正。"""
    client = FakeClient([
        tool_response("sky_dance", {}),
        text_response("抱歉，我没有这个工具。"),
    ])
    messages = [{"role": "user", "content": "跳个舞"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "Unknown: sky_dance"


def test_system_prompt_lists_workspace():
    """给模型的说明书里带着工作区路径，文件工具才有意义。"""
    from mini_claude.loop import SYSTEM
    assert str(tools.WORKDIR) in SYSTEM
