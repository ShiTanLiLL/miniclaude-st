"""Subagent：给子任务一段全新的 messages[]。

主代理的聊天记录越长，"找资料"这类脏活的中间结果就越容易把主任务
的思路淹掉。子代理的解法是上下文隔离：

    主代理出一张 task(prompt) 单
      -> 子代理在一段【全新空白】的 messages 里自己跑循环（最多 30 轮）
      -> 干完只把【最后一段文本】作为 tool_result 带回主代理
      -> 中间翻过的文件、跑过的命令，全部留在子代理的世界里，主代理看不见

子代理与主代理共用同一套工具、权限和钩子（execute_tool），
但拿不到 task 工具本身——否则它会派出自己的子代理，无限套娃。
"""

from .hooks import execute_tool, trigger_hooks
from .tools import TOOL_HANDLERS, TOOLS

MAX_TURNS = 30

# 子代理的会话凭证由宿主注入（REPL 或测试），而不是 import 时联网
SESSION = {"client": None, "model": None}


def bind(client, model) -> None:
    SESSION["client"] = client
    SESSION["model"] = model


SUB_SYSTEM = (
    "You are a focused coding subagent. Complete the given task, "
    "then return a concise final answer."
)


def extract_text(content) -> str:
    """把回复里的所有 text 块拼成一段字符串——这是子代理带回主代理的全部行李。"""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    )


def run_subagent(prompt: str) -> str:
    print("\n\033[35m[Subagent started]\033[0m")
    messages = [{"role": "user", "content": prompt}]   # 全新空白，与主代理零共享

    for _ in range(MAX_TURNS):
        response = SESSION["client"].messages.create(
            model=SESSION["model"], system=SUB_SYSTEM,
            messages=messages, tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            print("\033[35m[Subagent done]\033[0m")
            return extract_text(response.content) or "(no summary)"

        results = []
        for block in tool_calls:
            output = execute_tool(block, TOOL_HANDLERS)
            print(f"  \033[90m[sub] {block.name}: {output[:100]}\033[0m")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        messages.append({"role": "user", "content": results})

    print("\033[35m[Subagent stopped]\033[0m")
    return f"Subagent stopped after {MAX_TURNS} turns without a final answer."


TASK_TOOL = {
    "name": "task",
    "description": "Run a subagent with fresh conversation context and return its final text.",
    "input_schema": {
        "type": "object",
        "properties": {"prompt": {"type": "string", "minLength": 1}},
        "required": ["prompt"],
    },
}
