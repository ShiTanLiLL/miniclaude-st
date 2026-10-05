"""第 1 课离线测试：用假模型驱动 agent_loop 走完整个循环。

跑法：在仓库根目录执行
    .venv/bin/python -m pytest -q
不需要 API key。
"""

from fakes import FakeClient, text_response, tool_response
from mini_claude.loop import agent_loop, run_bash


def test_text_only_stops_immediately():
    """模型第一轮就纯说话 => 循环立刻结束，历史只多一条 assistant。"""
    client = FakeClient([text_response("你好呀")])
    messages = [{"role": "user", "content": "讲个笑话"}]

    agent_loop(messages, client, "fake-model")

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[-1]["content"][0].text == "你好呀"
    assert len(client.messages.calls) == 1  # 只调了一次模型


def test_bash_tool_roundtrip():
    """完整一圈：要工具 -> 执行 -> tool_result 回填 -> 模型总结收工。"""
    client = FakeClient([
        tool_response("echo hello-agent"),
        text_response("命令输出是 hello-agent"),
    ])
    messages = [{"role": "user", "content": "跑一下 echo"}]

    agent_loop(messages, client, "fake-model")

    assert [m["role"] for m in messages] == [
        "user", "assistant", "user", "assistant",
    ]
    tool_result = messages[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tool-1"
    assert tool_result["content"] == "hello-agent"  # 命令真的在本机执行了
    assert len(client.messages.calls) == 2


def test_dangerous_command_blocked():
    """危险命令不会真的执行，拦截信息作为 tool_result 交回模型。"""
    client = FakeClient([
        tool_response("rm -rf /"),
        text_response("好吧，那我换个安全的方式"),
    ])
    messages = [{"role": "user", "content": "删库跑路"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "Error: Dangerous command blocked"


def test_run_bash_direct():
    """工具函数本身的行为：正常输出 / 拦截 / 空输出。"""
    assert run_bash("echo abc") == "abc"
    assert run_bash("rm -rf /") == "Error: Dangerous command blocked"
    assert run_bash("true") == "(no output)"
