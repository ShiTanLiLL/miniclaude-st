"""第 6 课离线测试：子代理的上下文隔离、30 轮上限与权限继承。"""

from fakes import FakeClient, text_response, tool_response
from mini_claude import subagent
from mini_claude.loop import PARENT_TOOLS, agent_loop
from mini_claude.subagent import extract_text


def test_extract_text_joins_blocks():
    content = [SimpleNS("text", "第一段"), SimpleNS("tool_use", None), SimpleNS("text", "第二段")]
    assert extract_text(content) == "第一段\n第二段"


class SimpleNS:
    def __init__(self, type_, text):
        self.type = type_
        self.text = text or ""


def test_subagent_isolated_context(monkeypatch):
    """子代理跑在全新的 messages 里：主代理历史只有一条 task 的 tool_result。"""
    sub_client = FakeClient([
        tool_response("bash", {"command": "echo 中间过程谁也看不见"}, "s1"),
        text_response("调查结论：一切正常。"),
    ])
    monkeypatch.setattr(subagent, "SESSION", {"client": sub_client, "model": "fake-sub"})

    parent_client = FakeClient([
        tool_response("task", {"prompt": "去调查一下环境"}, "t1"),
        text_response("主任务完成。"),
    ])
    messages = [{"role": "user", "content": "派个分身去调查"}]

    agent_loop(messages, parent_client, "fake-parent")

    # 主代理的历史干干净净：只有那张 task 单和一句结论
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"][0]["content"] == "调查结论：一切正常。"
    assert "中间过程" not in str(messages)          # 子代理的中间过程没有漏进主历史

    # 子代理用的是自己的 system 和自己的消息列表
    sub_call = sub_client.messages.calls[0]
    assert sub_call["system"] == subagent.SUB_SYSTEM
    assert sub_call["messages"][0]["content"] == "去调查一下环境"


def test_subagent_cannot_spawn_subagents():
    """子代理的工具池里没有 task：防套娃。"""

    class ProbeMessages:
        def create(self, **kw):
            seen["tools"] = kw["tools"]
            return text_response("done")

    class ProbeClient:
        messages = ProbeMessages()

    seen = {}
    subagent.SESSION = {"client": ProbeClient(), "model": "m"}
    subagent.run_subagent("随便干点啥")
    names = [t["name"] for t in seen["tools"]]
    assert "task" not in names
    assert "bash" in names            # 干活工具照常配备


def test_subagent_turn_limit():
    """子代理一直不出总结：30 轮后被强制叫停，返回说明文字。"""

    class EndlessMessages:
        def __init__(self):
            self.calls = 0
        def create(self, **kw):
            self.calls += 1
            return tool_response("bash", {"command": "true"})

    class EndlessClient:
        def __init__(self):
            self.messages = EndlessMessages()

    subagent.SESSION = {"client": EndlessClient(), "model": "m"}
    result = subagent.run_subagent("无限干活")
    assert result == "Subagent stopped after 30 turns without a final answer."


def test_subagent_inherits_permission(monkeypatch):
    """子代理和主代理用同一套权限：死名单在子代理里照样拦。"""
    sub_client = FakeClient([
        tool_response("bash", {"command": "sudo ls"}, "s1"),
        text_response("被拦了，我换个方式也没问题。"),
    ])
    monkeypatch.setattr(subagent, "SESSION", {"client": sub_client, "model": "fake-sub"})

    result = subagent.run_subagent("用 sudo 看看目录")
    # 拦截话术只存在于子代理的内部历史里，带回主代理的只有最后那段文本
    assert result == "被拦了，我换个方式也没问题。"


def test_parent_pool_has_task_but_base_pool_does_not():
    """父代理工具池 = 基础池 + task；基础池保持纯净供子代理使用。"""
    from mini_claude import tools
    parent_names = [t["name"] for t in PARENT_TOOLS]
    base_names = [t["name"] for t in tools.TOOLS]
    assert "task" in parent_names
    assert "task" not in base_names


def test_loop_passes_parent_pool_to_model():
    client = FakeClient([text_response("好")])
    agent_loop([{"role": "user", "content": "hi"}], client, "fake")
    names = [t["name"] for t in client.messages.calls[0]["tools"]]
    assert "task" in names and "todo_write" in names
