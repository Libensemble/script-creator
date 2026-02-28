"""Skill ABC — base class for composable tool collections."""

from abc import ABC, abstractmethod


class Skill(ABC):
    """A composable collection of tools that can be added to the agent.

    Each skill provides:
    - get_tools() → list of LangChain StructuredTool
    - get_prompt_fragment() → optional text injected into the system prompt
    - setup() / teardown() → lifecycle hooks (e.g. connect MCP)
    """

    def __init__(self, config, archive):
        """
        Args:
            config: AgentConfig instance
            archive: ArchiveManager instance
        """
        self.config = config
        self.archive = archive

    @abstractmethod
    def get_tools(self):
        """Return list of LangChain StructuredTool instances."""
        ...

    def get_prompt_fragment(self):
        """Return text to inject into the system prompt, or empty string."""
        return ""

    async def setup(self):
        """Called before the agent loop starts. Override for async init."""
        pass

    async def teardown(self):
        """Called after the agent loop ends. Override for cleanup."""
        pass

    def set_mcp_session(self, session):
        """Inject an MCP session (called by orchestrator for MCP-dependent skills)."""
        pass
