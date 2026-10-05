"""第 1 课的核心：Agent Loop——一个 while 循环加一个 bash 工具。

    while True:
        response = 调用模型(messages, tools)
        没有工具调用 -> 模型认为做完了，返回
        执行每一个工具调用
        把结果作为 tool_result 塞回 messages，进入下一轮

模型决定何时调工具、何时停手；代码只负责执行并把结果递回去。
本模块只用标准库：真正的模型客户端由调用方传进来（inject），
这样测试时可以塞一个"假模型"，不联网也能驱动整个循环。
"""

import subprocess

SYSTEM = (
    "You are a coding agent. Use the bash tool to solve tasks. "
    "Act, don't explain."
)

# 工具的"说明书"：模型只能看到这段 JSON，看不到 run_bash 的代码。
BASH_TOOL = {
    "name": "bash",
    "description": "Run a shell command.",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}


def run_bash(command: str) -> str:
    """在本机真正执行一条 shell 命令，把输出（或错误信息）作为字符串返回。"""
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            errors="replace", timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except OSError as e:
        return f"Error: {e}"


def agent_loop(messages: list, client, model: str) -> None:
    """驱动对话，直到模型不再请求任何工具。

    messages 是"聊天记录本"，会被就地 append 增长，
    所以调用方（REPL）跨多轮提问时能保留完整历史。
    """
    while True:
        response = client.messages.create(
            model=model, system=SYSTEM, messages=messages,
            tools=[BASH_TOOL], max_tokens=8000,
        )

        # 1) 先把模型的回复原样记进历史
        messages.append({"role": "assistant", "content": response.content})

        # 2) 从回复里挑出工具调用单；一张都没有 => 模型收工
        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            return

        # 3) 替模型执行每一张调用单，攒成 tool_result 列表
        results = []
        for block in tool_calls:
            command = block.input["command"]
            print(f"\033[33m$ {command}\033[0m")
            output = run_bash(command)
            print(output[:200])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })

        # 4) 结果必须装在一条 user 消息里交还模型（协议规定），再进下一轮
        messages.append({"role": "user", "content": results})
