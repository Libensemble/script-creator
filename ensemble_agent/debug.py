"""Debug logging for agent message history."""

from datetime import datetime
from pathlib import Path


class DebugLogger:
    """Dumps message history and prompts to timestamped files."""

    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)

    def dump(self, content, stage=""):
        """Write content to a timestamped debug file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = self.output_dir / f"debug_{stage}_{timestamp}.txt"
        debug_file.parent.mkdir(parents=True, exist_ok=True)
        debug_file.write_text(content)
        print(f"  (Debug dumped to {debug_file})")

    def dump_messages(self, messages, stage=""):
        """Dump a list of LangChain messages."""
        lines = []
        for msg in messages:
            role = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", str(msg))
            lines.append(f"[{role}]\n{content}\n")
        self.dump("\n---\n".join(lines), stage)

    def dump_prompt(self, prompt_text, stage=""):
        """Print and optionally save a prompt."""
        slen = 15
        print(f"\n{'=' * slen} PROMPT TO AI ({stage}) {'=' * slen}")
        print(prompt_text)
        print(f"{'=' * slen} END AI PROMPT ({stage}) {'=' * slen}\n")
