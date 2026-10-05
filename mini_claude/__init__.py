"""mini_claude —— 逐课复现 learn-claude-code 的迷你 Agent Harness。

当前能力（第 7 课后）：
- Agent Loop：模型决定何时用工具、何时停手
- 工具池：bash / read_file / write_file / edit_file / glob / todo_write / task / load_skill
- 权限规则 + 四个钩子扩展点 + execute_tool 共享执行管线
- TodoWrite：先计划后执行，三态清单 + 3 轮未更新提醒
- Subagent：子任务独立上下文，最终文本作为 tool_result 返回
- Skill Loading：技能目录常驻 prompt，正文按需加载（pyyaml 登场）
"""
