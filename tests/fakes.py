"""测试用的"假模型"工具箱。

不联网、不花钱：把模型要说的每一步提前写成剧本（一串假响应），
FakeClient 按顺序吐出来，agent_loop 就能被 pytest 完整驱动。
这招学自原项目 tests/ 的做法，后面每一课的测试都靠它。

第 2 课升级：tool_response 支持任意工具（不再只有 bash），
并拆出 tool_block 方便在一条回复里塞多张调用单。
"""

from types import SimpleNamespace


def text_response(text: str):
    """构造一个"只说话、不调工具"的模型回复。"""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)]
    )


def tool_block(name: str, arguments: dict, tool_use_id: str = "tool-1"):
    """构造一张工具调用单（一条回复里可以有很多张）。"""
    return SimpleNamespace(
        type="tool_use", id=tool_use_id, name=name, input=arguments,
    )


def tool_response(name: str, arguments: dict, tool_use_id: str = "tool-1"):
    """构造一个"恰好要调用一个工具"的模型回复。"""
    return SimpleNamespace(content=[tool_block(name, arguments, tool_use_id)])


class FakeMessages:
    """按剧本出牌，并记下每次收到的调用参数，供断言用。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("模型被调用的次数超出了剧本")
        return self.responses.pop(0)


class FakeClient:
    """Anthropic 客户端的替身：只在 .messages.create 这一点上以假乱真。"""

    def __init__(self, responses):
        self.messages = FakeMessages(responses)
