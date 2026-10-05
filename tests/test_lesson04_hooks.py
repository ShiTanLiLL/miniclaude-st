"""第 4 课离线测试：四个扩展点、拦截与放行、Stop 钩子的强制续跑。"""

from types import SimpleNamespace

import pytest

from fakes import FakeClient, text_response, tool_response
from mini_claude import hooks
from mini_claude.loop import agent_loop


@pytest.fixture(autouse=True)
def clean_hooks():
    """每个用例前后都把钩子注册表恢复出厂状态，用例之间互不污染。"""
    saved = {k: list(v) for k, v in hooks.HOOKS.items()}
    yield
    hooks.HOOKS.clear()
    hooks.HOOKS.update(saved)


def test_first_non_none_hook_wins():
    """钩子按注册顺序跑；第一个返回非 None 的说了算，后面的不再跑。"""
    fired = []
    hooks.register_hook("PreToolUse", lambda b: (fired.append("A"), "A拦截了")[1])
    hooks.register_hook("PreToolUse", lambda b: fired.append("B"))
    safe_block = SimpleNamespace(name="bash", input={"command": "echo hi"})
    result = hooks.trigger_hooks("PreToolUse", safe_block)
    assert result == "A拦截了"
    assert fired == ["A"]  # B 根本没机会跑


def test_pretooluse_block_skips_execution():
    """自定义 PreToolUse 钩子拦截后：命令不执行，话术作为结果回模型。"""
    hooks.register_hook("PreToolUse", lambda b: "测试专用拦截" if b.name == "bash" else None)

    client = FakeClient([
        tool_response("bash", {"command": "echo should-not-run"}),
        text_response("收到，我不跑了。"),
    ])
    messages = [{"role": "user", "content": "跑 echo"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "测试专用拦截"


def test_posttooluse_watches_output():
    """PostToolUse 在结果定稿后跑，能拿到完整输出。"""
    seen = []
    hooks.register_hook("PostToolUse", lambda b, out: seen.append((b.name, out)))

    client = FakeClient([
        tool_response("bash", {"command": "echo hook-test"}),
        text_response("好了"),
    ])
    agent_loop([{"role": "user", "content": "x"}], client, "fake-model")

    assert seen == [("bash", "hook-test")]


def test_stop_hook_can_force_continue():
    """Stop 钩子返回内容 = 否决收工：循环把内容当新任务继续跑。"""
    calls = {"n": 0}

    def bossy_stop(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return "还没完，继续检查一遍。"   # 第一次否决
        return None                          # 第二次放行

    hooks.register_hook("Stop", bossy_stop)
    client = FakeClient([
        text_response("我觉得做完了。"),                    # 第一次想收工
        tool_response("bash", {"command": "echo recheck"}),  # 被迫续跑后干活
        text_response("这次真完成了。"),
    ])
    messages = [{"role": "user", "content": "任务"}]

    agent_loop(messages, client, "fake-model")

    assert len(client.messages.calls) == 3        # 模型被拉回来多跑了一轮
    roles = [m["role"] for m in messages]
    assert roles.count("user") == 3               # 原始任务 + Stop 否决意见 + 工具结果
    assert "还没完，继续检查一遍。" in messages[2]["content"]
    assert messages[-1]["content"][0].text == "这次真完成了。"


def test_builtin_permission_hook_still_blocks():
    """搬家验收：第 3 课的拦截行为通过钩子原样复现（死名单路径）。"""
    client = FakeClient([
        tool_response("bash", {"command": "sudo ls"}),
        text_response("好的，不用 sudo 了。"),
    ])
    messages = [{"role": "user", "content": "用 sudo 看看"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"] == "Blocked: 'sudo' is on the deny list"


def test_hook_registration_is_order_sensitive():
    """出厂钩子的顺序：permission 先于 log（先拦截，干净单子才轮到记流水账）。"""
    names = [fn.__name__ for fn in hooks.HOOKS["PreToolUse"]]
    assert names == ["permission_hook", "log_hook"]
