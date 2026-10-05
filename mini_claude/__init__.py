"""mini_claude —— 逐课复现 learn-claude-code 的迷你 Agent Harness。

当前能力（第 3 课后）：
- Agent Loop：模型决定何时用工具、何时停手
- 五件套工具：bash / read_file / write_file / edit_file / glob，查表分发
- 权限三道闸：硬拒绝名单 -> 规则匹配 -> 用户 y/N 确认
"""
