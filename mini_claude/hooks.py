"""钩子系统：把"循环前后该做的杂事"从循环里搬出去。

第 3 课的权限检查焊在循环体内；本课把它改造成 PreToolUse 钩子。
循环从此只说一句话："到点了，钩子们请上场"——它不再认识权限、日志这些具体业务。

四个扩展点：
  UserPromptSubmit  用户输入进 messages 之前（由 REPL 调用）
  PreToolUse        每张工具调用单执行之前（返回非 None = 拦截）
  PostToolUse       工具执行之后（结果已定，只能旁观/告警）
  Stop              模型想收工时（返回非 None = 强制循环继续）

trigger_hooks 的约定：按注册顺序逐个调用；第一个返回非 None 的说了算，
后面的钩子不再跑。返回 None 表示"我只是旁观，不发表意见"。
"""

from . import permission

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}


def register_hook(event: str, callback) -> None:
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


def execute_tool(block, handlers: dict) -> str:
    """一次工具调用的标准流程：过闸 -> 执行（异常兜底）-> 旁观。

    第 6 课从循环里抽出来：主代理和子代理共用同一套执行规矩。
    """
    blocked = trigger_hooks("PreToolUse", block)
    if blocked:
        return str(blocked)

    handler = handlers.get(block.name)
    try:
        output = handler(**block.input) if handler else f"Unknown: {block.name}"
    except Exception as e:
        output = f"Error: {e}"

    trigger_hooks("PostToolUse", block, output)
    return str(output)


def permission_hook(block):
    """PreToolUse：第 3 课的三道闸搬到这里（规则本身仍在 permission.py，不复制）。"""
    if block.name == "bash":
        reason = permission.check_deny_list(block.input.get("command", ""))
        if reason:
            print(f"\n\033[31m[blocked] {reason}\033[0m")
            return reason
    reason = permission.check_rules(block.name, block.input)
    if reason:
        print(f"\n\033[33m[permission] {reason}\033[0m")
        print(f"   Tool: {block.name}({block.input})")
        choice = input("   Allow? [y/N] ").strip().lower()
        if choice not in ("y", "yes"):
            return "Permission denied by user"
    return None


def log_hook(block):
    """PreToolUse：每次工具调用都留一笔流水账。"""
    args_preview = str(list(block.input.values())[:2])[:60]
    print(f"\033[90m[HOOK] {block.name}({args_preview})\033[0m")
    return None


def large_output_hook(block, output):
    """PostToolUse：输出太大时告警（截断是 tools 层的事，这里只提醒）。"""
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] Large output from {block.name}: {len(str(output))} chars\033[0m")
    return None


def context_inject_hook(query: str):
    """UserPromptSubmit：用户输入进场时点个名（第 9 课记忆注入也走这个位）。"""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {tools.WORKDIR}\033[0m")
    return None


def summary_hook(messages: list):
    """Stop：模型收工前统计本次会话用了多少次工具。"""
    tool_count = sum(
        1 for m in messages
        for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None


# ---- 出厂自带的钩子（顺序即触发顺序：permission 在前，先拦再记日志）----
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
