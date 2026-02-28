"""Reference docs skill — static markdown lookups for generators, APOSMM, etc."""

from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from .base import Skill

DOCS_DIR = Path(__file__).parent / "docs"


class ReadSkillInput(BaseModel):
    topic: str = Field(
        description="Topic to look up: 'aposmm', 'generators', or 'script_structure'"
    )


class ReferenceDocsSkill(Skill):
    """Provides the read_skill tool and injects loaded docs into the system prompt."""

    def _load_all_docs(self):
        """Load all .md files from the docs directory."""
        if not DOCS_DIR.exists():
            return ""
        parts = []
        for f in sorted(DOCS_DIR.glob("*.md")):
            parts.append(f.read_text().strip())
        if not parts:
            return ""
        return "Reference information:\n\n" + "\n\n---\n\n".join(parts)

    def _list_topics(self):
        """List available topic names (filenames without .md)."""
        if not DOCS_DIR.exists():
            return []
        return [f.stem for f in sorted(DOCS_DIR.glob("*.md"))]

    def get_tools(self):
        async def read_skill_tool(topic: str) -> str:
            doc_file = DOCS_DIR / f"{topic}.md"
            if not doc_file.exists():
                available = ", ".join(self._list_topics())
                return f"ERROR: Unknown topic '{topic}'. Available: {available}"
            return doc_file.read_text()

        return [
            StructuredTool(
                name="read_skill",
                description=(
                    "Look up reference documentation for a topic. "
                    f"Available topics: {', '.join(self._list_topics())}"
                ),
                args_schema=ReadSkillInput,
                coroutine=read_skill_tool,
            ),
        ]

    def get_prompt_fragment(self):
        return self._load_all_docs()
