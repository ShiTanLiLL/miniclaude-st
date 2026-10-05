"""权限系统：在"模型想动手"和"真的动手"之间插三道闸。

    第一道 硬拒绝：命中 DENY_LIST 直接拦，没商量。
    第二道 规则匹配：越界文件、破坏性命令，按规则表识别。
    第三道 用户确认：拿不准的停下来问你，y/N。

拦截永远不是抛异常——而是让 tool_result 带着拒绝原因回到模型，
让它自己换一条路。这是 Harness 对模型说话的方式。
"""

import re

from . import tools

# 第一道：死名单。命中的命令不管三七二十一，一律不执行。
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]


def check_deny_list(command: str) -> str | None:
    """命中死名单返回拒绝理由，安全返回 None。"""
    for pattern in DENY_LIST:
        if pattern in command:
            return f"Blocked: '{pattern}' is on the deny list"
    return None


# 第二道：规则匹配。判断"rm/del 是不是真的作为一条命令出现"，
# 避免 echo firm、mkdir arm 这种无辜字符串被误伤。
DESTRUCTIVE_COMMAND_WORD = re.compile(
    r"(?i)(?:^|[;&|()\n])\s*(?:rm|del)(?=\s|$|[;&|()])"
)


def contains_destructive_command(command: str) -> bool:
    return bool(DESTRUCTIVE_COMMAND_WORD.search(command))


# 规则表：每条规则管几个工具，check 返回 True 表示"可疑，需要过闸"。
PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (tools.WORKDIR / args.get("path", "")).resolve().is_relative_to(tools.WORKDIR),
     "message": "Writing outside workspace"},
    {"tools": ["bash"],
     "check": lambda args: contains_destructive_command(args.get("command", "")) or
                any(kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]),
     "message": "Potentially destructive command"},
]


def check_rules(tool_name: str, args: dict) -> str | None:
    """逐条规则匹配；命中返回规则 message，全部安全返回 None。"""
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


# 第三道：用户确认。程序停下来，把决定权交还给人。
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m[permission] {reason}\033[0m")
    print(f"   Tool: {tool_name}({args})")
    choice = input("   Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


def check_permission(block) -> bool:
    """三道闸串起来跑一遍。返回 False = 这张调用单不许执行。"""
    if block.name == "bash":
        reason = check_deny_list(block.input.get("command", ""))
        if reason:
            print(f"\n\033[31m[blocked] {reason}\033[0m")
            return False
    reason = check_rules(block.name, block.input)
    if reason:
        if ask_user(block.name, block.input, reason) == "deny":
            return False
    return True
