"""Agent Loop——整个项目唯一的主干道。

第 1 课：一个 bash 工具，循环里硬编码调用 run_bash。
第 2 课：工具搬进 tools.py，循环改成查 TOOL_HANDLERS 分发。
第 3 课：执行工具前先过 check_permission 三道闸。
第 4 课：三道闸改造成 PreToolUse 钩子，循环只认 trigger_hooks。
第 5 课：todo_write 计划清单 + 3 轮未更新注入 <reminder>。
第 6 课：task 工具接入子代理（独立 messages），工具执行抽成
        hooks.execute_tool 供主/子代理共用。
"""

from .hooks import execute_tool, trigger_hooks
from .skills import LOADER
from .subagent import TASK_TOOL, run_subagent
from .tools import TOOLS, TOOL_HANDLERS, WORKDIR

REMINDER_ROUNDS = 3


def build_system_prompt() -> str:
    """组装 system prompt：岗位说明 + 技能目录（目录常驻，正文按需）。"""
    return (
        f"You are a coding agent. Workspace: {WORKDIR}. "
        "Use the available tools to solve tasks. Act, don't explain. "
        "All destructive operations require user approval. "
        "Before starting any multi-step task, use todo_write to plan your steps. "
        "Update status as you go. "
        "Use task for focused exploration or a self-contained subtask.\n\n"
        f"Skills available:\n{LOADER.catalog()}\n\n"
        "Use load_skill to read the full instructions when a skill applies."
    )


SYSTEM = build_system_prompt()

# 父代理的工具池 = 基础工具 + task。子代理只用基础池，拿不到 task（防套娃）。
PARENT_TOOLS = [*TOOLS, TASK_TOOL]
PARENT_HANDLERS = {**TOOL_HANDLERS, "task": run_subagent}


def agent_loop(messages: list, client, model: str) -> None:
    """驱动对话，直到模型不再请求任何工具（且 Stop 钩子不反对）。

    messages 是"聊天记录本"，会被就地 append 增长，
    所以调用方（REPL）跨多轮提问时能保留完整历史。
    """
    rounds_since_todo = 0
    while True:
        response = client.messages.create(
            model=model, system=SYSTEM, messages=messages,
            tools=PARENT_TOOLS, max_tokens=8000,
        )

        # 1) 先把模型的回复原样记进历史
        messages.append({"role": "assistant", "content": response.content})

        # 2) 从回复里挑出工具调用单；一张都没有 => 模型想收工，Stop 钩子有权否决
        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                # 有钩子反对收工：把它的意见作为新任务塞回去，循环继续
                messages.append({"role": "user", "content": force})
                continue
            return

        # 3) 过闸改走钩子：PreToolUse 拦截 -> 查表执行 -> PostToolUse 旁观
        #    （过闸/执行/旁观都在 hooks.execute_tool 里，第 6 课起主/子代理共用）
        results = []
        used_todo = False
        for block in tool_calls:
            print(f"\033[36m> {block.name}\033[0m")
            output = execute_tool(block, PARENT_HANDLERS)
            print(str(output)[:200])

            if block.name == "todo_write":
                used_todo = True

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(output),
            })

        # 第 5 课：连续 3 轮没更新计划，就在结果里捎一句提醒
        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        if rounds_since_todo >= REMINDER_ROUNDS:
            results.append({"type": "text",
                            "text": "<reminder>Update your todos.</reminder>"})
            rounds_since_todo = 0

        # 4) 结果必须装在一条 user 消息里交还模型（协议规定），再进下一轮
        messages.append({"role": "user", "content": results})
