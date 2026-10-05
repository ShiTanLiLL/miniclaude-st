"""mini_claude —— 逐课复现 learn-claude-code 的迷你 Agent Harness。

当前能力（第 4 课后）：
- Agent Loop：模型决定何时用工具、何时停手
- 五件套工具：bash / read_file / write_file / edit_file / glob，查表分发
- 权限规则：死名单 / 规则匹配 / 用户确认（现已包装为 PreToolUse 钩子）
- 四个钩子扩展点：UserPromptSubmit / PreToolUse / PostToolUse / Stop
"""
