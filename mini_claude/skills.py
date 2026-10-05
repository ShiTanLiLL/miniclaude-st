"""Skill Loading：目录常驻 prompt，正文用到才加载。

把知识塞给模型有两种极端：全量前置（整本说明书进 SYSTEM，每次调用都背着）
和临时抱佛脚（要用时才发现没有）。折中方案是两级加载：

    启动时  扫描 skills/*/SKILL.md，只取 frontmatter 的名称+描述
            -> 一行行清单放进 SYSTEM（便宜，常驻）
    运行时  模型判断某条技能用得上 -> 调 load_skill(name)
            -> 整份 SKILL.md 作为 tool_result 进入对话（按需，一次性）

SKILL.md 的头部是一小段 YAML frontmatter（--- 包起来的元数据），
pyyaml 在这里第一次登场。
"""

from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """拆出文件头部的 YAML 元数据和正文。没有 frontmatter 就原样奉还。"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1)
         if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing_index is None:
        return {}, text

    frontmatter = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1:]).strip()
    try:
        metadata = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, body


class SkillLoader:
    """启动时扫描一遍技能目录，之后只做查询，不再碰磁盘。"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return

        skills_root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            if (not manifest.is_file()
                    or not manifest.resolve().is_relative_to(skills_root)):
                continue
            content = manifest.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
            # 名称：frontmatter 优先，缺失则退回目录名
            raw_name = metadata.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            name = name or manifest.parent.name
            # 描述：frontmatter 优先，缺失则退回正文第一行
            raw_description = metadata.get("description")
            description = (raw_description.strip()
                           if isinstance(raw_description, str) else "")
            description = description or body.split("\n", 1)[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {
                "name": name,
                "description": description,
                "content": content,      # 整份文件原文，按需才出库
            }

    def catalog(self) -> str:
        """渲染成 SYSTEM 里的一行行清单——常驻部分，便宜。"""
        if not self.skills:
            return "(no skills found)"
        return "\n".join(
            f"- {skill['name']}: {skill['description']}"
            for skill in self.skills.values()
        )

    def load(self, name: str) -> str:
        """按需加载：命中返回整份 SKILL.md，没命中报错并列出可选清单。"""
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"


LOADER = SkillLoader(SKILLS_DIR)

SKILL_TOOL = {
    "name": "load_skill",
    "description": "Load the full SKILL.md content by skill name.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
}
