"""Skill registry and loader."""

from .base import Skill
from .file_ops import FileOpsSkill
from .runner import RunnerSkill
from .generator import GeneratorSkill
from .reference_docs import ReferenceDocsSkill

# Registry: skill name → class
SKILL_REGISTRY = {
    "file_ops": FileOpsSkill,
    "runner": RunnerSkill,
    "generator": GeneratorSkill,
    "reference_docs": ReferenceDocsSkill,
}


def load_skills(skill_names, config, archive):
    """Instantiate skills by comma-separated name string.

    Args:
        skill_names: e.g. "file_ops,runner,generator,reference_docs"
        config: AgentConfig
        archive: ArchiveManager

    Returns:
        list of Skill instances
    """
    skills = []
    for name in skill_names.split(","):
        name = name.strip()
        if not name:
            continue
        cls = SKILL_REGISTRY.get(name)
        if cls is None:
            available = ", ".join(SKILL_REGISTRY.keys())
            raise ValueError(f"Unknown skill '{name}'. Available: {available}")
        skills.append(cls(config, archive))
    return skills
