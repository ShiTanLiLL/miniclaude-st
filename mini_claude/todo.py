"""TodoWrite：让 Agent 先列计划、对表干活。

模型通过 todo_write 工具提交整份清单（全量替换，不是逐条增删）；
清单由 Harness 保管并校验。三态状态机：
    [ ] pending     还没开始
    [>] in_progress  正在做（全局只允许一个）
    [x] completed    完成

一个管理细节：模型连续 3 轮没更新清单，循环会往工具结果里
塞一条 <reminder> 提醒它对表——计划的维护也要有督促。
"""

import ast
import json

MAX_TODOS = 20
VALID_STATUS = ("pending", "in_progress", "completed")
MARKERS = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}


class TodoManager:
    """清单的唯一保管人。模型每次提交整份清单，这里负责校验和渲染。"""

    def __init__(self):
        self.items: list[dict] = []

    def update(self, todos: list | str) -> str:
        """全量替换清单，返回渲染结果。任何不合法都抛 ValueError。"""
        if isinstance(todos, str):
            # 模型有时把清单当字符串交上来：先试 JSON，再试 Python 字面量
            try:
                todos = json.loads(todos)
            except json.JSONDecodeError:
                try:
                    todos = ast.literal_eval(todos)
                except (SyntaxError, ValueError) as e:
                    raise ValueError("todos must be a list or JSON array string") from e

        if not isinstance(todos, list):
            raise ValueError("todos must be a list")
        if len(todos) > MAX_TODOS:
            raise ValueError(f"Max {MAX_TODOS} todos allowed")

        validated = []
        in_progress_count = 0
        for index, todo in enumerate(todos):
            if not isinstance(todo, dict):
                raise ValueError(f"todos[{index}] must be an object")
            content = str(todo.get("content", "")).strip()
            status = str(todo.get("status", "pending")).lower()
            if not content:
                raise ValueError(f"todos[{index}] requires content")
            if status not in VALID_STATUS:
                raise ValueError(f"todos[{index}] has invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"content": content, "status": status})

        if in_progress_count > 1:
            raise ValueError("Only one todo can be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        """渲染成给模型（和终端）看的清单视图。"""
        if not self.items:
            return "No todos."

        lines = [f"{MARKERS[t['status']]} {t['content']}" for t in self.items]
        done = sum(t["status"] == "completed" for t in self.items)
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)


TODO = TodoManager()


def run_todo_write(todos: list | str) -> str:
    """工具入口：校验失败返回错误字符串（不抛异常，错误是模型的反馈不是事故）。"""
    try:
        output = TODO.update(todos)
    except ValueError as e:
        return f"Error: {e}"
    print(f"\n\033[33m## Current Tasks\033[0m\n{output}")
    return output


TODO_TOOL = {
    "name": "todo_write",
    "description": "Create and manage a task list for your current coding session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "maxItems": MAX_TODOS,
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "minLength": 1},
                        "status": {"type": "string",
                                   "enum": ["pending", "in_progress", "completed"]},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["todos"],
    },
}
