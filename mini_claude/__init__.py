"""mini_claude —— 逐课复现 learn-claude-code 的迷你 Agent Harness。

当前能力（第 5 课后）：
- Agent Loop：模型决定何时用工具、何时停手
- 工具池：bash / read_file / write_file / edit_file / glob / todo_write
- 权限规则 + 四个钩子扩展点
- TodoWrite：先计划后执行，三态清单 + 3 轮未更新提醒
"""
