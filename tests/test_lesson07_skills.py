"""第 7 课离线测试：frontmatter 解析、目录渲染、按需加载。"""

from pathlib import Path

from fakes import FakeClient, text_response, tool_response
from mini_claude import skills
from mini_claude.loop import SYSTEM, agent_loop


def make_skill(tmp_path: Path, name: str, text: str):
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d


def loader(tmp_path):
    return skills.SkillLoader(tmp_path)


# ---------- frontmatter 解析 ----------

def test_parse_frontmatter_basic():
    meta, body = skills.parse_frontmatter(
        "---\nname: demo\ndescription: 测试技能\n---\n\n# 正文\n内容"
    )
    assert meta == {"name": "demo", "description": "测试技能"}
    assert body.startswith("# 正文")


def test_parse_frontmatter_missing_or_broken():
    assert skills.parse_frontmatter("没有头部") == ({}, "没有头部")
    # 只有开头 --- 没有结尾：视为没有 frontmatter
    meta, body = skills.parse_frontmatter("---\nname: demo\n正文")
    assert meta == {}
    assert "demo" in body


# ---------- 扫描与目录 ----------

def test_scan_and_catalog(tmp_path):
    make_skill(tmp_path, "code-review",
               "---\nname: code-review\ndescription: 评审代码\n---\n正文A")
    make_skill(tmp_path, "pdf",
               "---\nname: pdf\ndescription: 处理PDF\n---\n正文B")
    out = loader(tmp_path).catalog()
    assert out.splitlines() == [
        "- code-review: 评审代码",
        "- pdf: 处理PDF",
    ]


def test_fallbacks_dir_name_and_first_line(tmp_path):
    """frontmatter 缺 name 用目录名；缺 description 用正文第一行。"""
    make_skill(tmp_path, "my-skill", "---\n---\n# 第一行是标题\n正文")
    skill = loader(tmp_path).skills["my-skill"]
    assert skill["description"] == "第一行是标题"


def test_empty_dir_catalog(tmp_path):
    assert loader(tmp_path).catalog() == "(no skills found)"


# ---------- 按需加载 ----------

def test_load_returns_full_content(tmp_path):
    make_skill(tmp_path, "demo",
               "---\nname: demo\ndescription: x\n---\n第一行正文\n第二行正文")
    content = loader(tmp_path).load("demo")
    assert content.startswith("---\nname: demo")
    assert "第二行正文" in content       # 整份原文，包括 frontmatter


def test_load_unknown_lists_available(tmp_path):
    make_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: x\n---\nA")
    out = loader(tmp_path).load("不存在")
    assert out == "Error: Unknown skill '不存在'. Available: alpha"


# ---------- 与循环的接线 ----------

def test_real_repo_skills_in_system_prompt():
    """仓库自带的四个示例技能应该出现在 system prompt 目录里。"""
    for expected in ("code-review", "pdf", "agent-builder", "mcp-builder"):
        assert expected in SYSTEM


def test_load_skill_through_loop():
    """模型调 load_skill：整份 SKILL.md 作为 tool_result 回进对话。"""
    client = FakeClient([
        tool_response("load_skill", {"name": "pdf"}),
        text_response("已按 pdf 技能的流程准备处理。"),
    ])
    messages = [{"role": "user", "content": "帮我读一下这个 PDF"}]

    agent_loop(messages, client, "fake-model")

    result = messages[2]["content"][0]["content"]
    assert result.startswith("---\nname: pdf")
    assert "# PDF Processing Skill" in result


def test_skill_tool_registered():
    from mini_claude import tools
    # 注意用 == 而不是 is：每次访问 LOADER.load 都生成新的绑定方法对象
    assert tools.TOOL_HANDLERS["load_skill"] == skills.LOADER.load
    assert any(t["name"] == "load_skill" for t in tools.TOOLS)
