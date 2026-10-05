"""Agent Loop——整个项目唯一的主干道。

第 1 课：一个 bash 工具，循环里硬编码调用 run_bash。
第 2 课：工具搬进 tools.py，循环改成查 TOOL_HANDLERS 分发。
第 3 课：执行工具前先过 check_permission 三道闸——循环里只加了一个 if。
"""

from .permission import check_permission
from .tools import TOOLS, TOOL_HANDLERS, WORKDIR

SYSTEM = (
    f"You are a coding agent. Workspace: {WORKDIR}. "
    "Use the available tools to solve tasks. Act, don't explain. "
    "All destructive operations require user approval."
)


def agent_loop(messages: list, client, model: str) -> None:
    """驱动对话，直到模型不再请求任何工具。

    messages 是"聊天记录本"，会被就地 append 增长，
    所以调用方（REPL）跨多轮提问时能保留完整历史。
    """
    while True:
        response = client.messages.create(
            model=model, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )

        # 1) 先把模型的回复原样记进历史
        messages.append({"role": "assistant", "content": response.content})

        # 2) 从回复里挑出工具调用单；一张都没有 => 模型收工
        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            return

        # 3) 过闸：三道权限检查通过才轮到分发表；被拒则把拒绝话术交回模型
        results = []
        for block in tool_calls:
            print(f"\033[36m> {block.name}\033[0m")
            if not check_permission(block):
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Permission denied.",
                })
                continue
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"
            print(str(output)[:200])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        # 4) 结果必须装在一条 user 消息里交还模型（协议规定），再进下一轮
        messages.append({"role": "user", "content": results})
