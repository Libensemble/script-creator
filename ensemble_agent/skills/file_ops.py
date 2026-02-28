"""File operations skill — read, write, list files in the work directory."""

from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from .base import Skill


class ReadFileInput(BaseModel):
    filepath: str = Field(description="Path to file relative to work directory")


class WriteFileInput(BaseModel):
    filepath: str = Field(description="Path to file relative to work directory")
    content: str = Field(description="Full content to write")


class ListFilesInput(BaseModel):
    pass


class FileOpsSkill(Skill):
    """Provides read_file, write_file, and list_files tools."""

    def get_tools(self):
        work_dir = self.archive.work_dir
        archive = self.archive

        async def read_file_tool(filepath: str) -> str:
            file_path = work_dir / filepath
            if not file_path.exists():
                return f"ERROR: File '{filepath}' not found"
            return file_path.read_text()

        async def write_file_tool(filepath: str, content: str) -> str:
            try:
                (work_dir / filepath).write_text(content)
                archive.start("fix")
                archive.archive_scripts()
                print(f"- Saved: {work_dir / filepath}", flush=True)
                return f"SUCCESS: Wrote {filepath}"
            except Exception as e:
                return f"ERROR: {e}"

        async def list_files_tool() -> str:
            py_files = list(work_dir.glob("*.py"))
            if not py_files:
                return "No Python files found"
            return "Files:\n" + "\n".join(f"- {f.name}" for f in py_files)

        return [
            StructuredTool(
                name="read_file",
                description="Read a file to inspect its contents.",
                args_schema=ReadFileInput,
                coroutine=read_file_tool,
            ),
            StructuredTool(
                name="write_file",
                description="Write/overwrite a file to fix scripts.",
                args_schema=WriteFileInput,
                coroutine=write_file_tool,
            ),
            StructuredTool(
                name="list_files",
                description="List Python files in working directory.",
                args_schema=ListFilesInput,
                coroutine=list_files_tool,
            ),
        ]
