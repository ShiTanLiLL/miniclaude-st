"""第 5 课离线测试：TodoManager 状态机 + 循环的提醒与异常兜底。"""

from fakes import FakeClient, text_response, tool_response
from mini_claude import todo, tools
from mini_claude.loop import REMINDER_ROUNDS, agent_loop


def fresh():
    return todo.TodoManager()


# ---------- TodoManager 校验与渲染 ----------

def test_update_and_render():
    m = fresh()
    out = m.update([
        {"content": "读代码", "status": "completed"},
        {"content": "改代码", "status": "in_progress"},
        {"content": "跑测试", "status": "pending"},
    ])
    assert out.splitlines() == [
        "[x] 读代码", "[>] 改代码", "[ ] 跑测试", "", "(1/3 completed)",
    ]


def test_accepts_json_string():
    m = fresh()
    assert "读代码" in m.update('[{"content": "读代码", "status": "pending"}]')


def test_rejects_two_in_progress():
    m = fresh()
    try:
        m.update([{"content": "a", "status": "in_progress"},
                  {"content": "b", "status": "in_progress"}])
        raise AssertionError("应当拒绝两个 in_progress")
    except ValueError as e:
        assert "in_progress" in str(e)


def test_rejects_bad_status_and_empty_content():
    m = fresh()
    for bad in ({"content": "x", "status": "done"},
                {"content": "  ", "status": "pending"},
                {"status": "pending"}):
        try:
            m.update([bad])
            raise AssertionError(f"应当拒绝 {bad}")
        except ValueError:
            pass


def test_rejects_over_20():
    m = fresh()
    try:
        m.update([{"content": str(i), "status": "pending"} for i in range(21)])
        raise AssertionError("应当拒绝超过 20 条")
    except ValueError as e:
        assert "20" in str(e)


def test_empty_render():
    assert fresh().render() == "No todos."


# ---------- 工具入口 ----------

def test_run_todo_write_error_is_string(monkeypatch):
    """校验失败不抛异常：错误作为字符串交回模型。"""
    monkeypatch.setattr(todo, "TODO", fresh())
    assert todo.run_todo_write("这不是清单").startswith("Error: ")


def test_run_todo_write_success(monkeypatch):
    monkeypatch.setattr(todo, "TODO", fresh())
    out = todo.run_todo_write([{"content": "第一步", "status": "in_progress"}])
    assert out == "[>] 第一步\n\n(0/1 completed)"


# ---------- 循环集成 ----------

def test_handler_exception_becomes_tool_result():
    """第 5 课新兜底：handler 抛异常（如缺参数）不再炸循环。"""
    client = FakeClient([
        tool_response("bash", {}),   # 缺 command 参数，调用时会 TypeError
        text_response("好吧，参数忘填了。"),
    ])
    messages = [{"role": "user", "content": "随便跑点什么"}]

    agent_loop(messages, client, "fake-model")

    assert messages[2]["content"][0]["content"].startswith("Error: ")


def test_reminder_after_three_idle_rounds():
    """连续 3 轮不碰 todo_write：第 3 轮的结果里混进一条 <reminder> 文本。"""
    script = [tool_response("bash", {"command": f"echo r{i}"}) for i in range(1, 5)]
    script.append(text_response("干完了"))
    client = FakeClient(script)
    messages = [{"role": "user", "content": "连跑四次 echo"}]

    agent_loop(messages, client, "fake-model")

    third_results = messages[6]["content"]    # 第 3 轮的工具结果消息
    assert any(
        isinstance(b, dict) and b.get("type") == "text"
        and "<reminder>" in b.get("text", "")
        for b in third_results
    )
    fourth_results = messages[8]["content"]   # 提醒后计数器归零，不再提醒
    assert not any(
        isinstance(b, dict) and b.get("type") == "text" and "<reminder>" in b.get("text", "")
        for b in fourth_results
    )


def test_todo_write_resets_reminder_counter(monkeypatch):
    """中途更新过一次清单，计数器归零：4 轮内不再提醒。"""
    monkeypatch.setattr(todo, "TODO", fresh())
    script = [
        tool_response("bash", {"command": "echo 1"}, "t1"),
        tool_response("todo_write", {"todos": [{"content": "列个计划", "status": "completed"}]}, "t2"),
        tool_response("bash", {"command": "echo 3"}, "t3"),
        tool_response("bash", {"command": "echo 4"}, "t4"),
        text_response("完成"),
    ]
    client = FakeClient(script)
    messages = [{"role": "user", "content": "干活"}]

    agent_loop(messages, client, "fake-model")

    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else []
        for b in blocks:
            if isinstance(b, dict):
                assert "<reminder>" not in str(b.get("text", ""))


def test_system_prompt_has_planning_guidance():
    from mini_claude.loop import SYSTEM
    assert "todo_write" in SYSTEM


def test_todo_tool_registered():
    """第 2 课的查表分发兑现承诺：加新工具只登记两笔。"""
    assert tools.TOOL_HANDLERS["todo_write"] is todo.run_todo_write
    assert any(t["name"] == "todo_write" for t in tools.TOOLS)


# 供断言用的常量 sanity check（防止有人悄悄改提醒阈值）
def test_reminder_rounds_constant():
    assert REMINDER_ROUNDS == 3
