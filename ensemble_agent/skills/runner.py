"""Script runner skill — execute scripts with timeout and archive output."""

import subprocess

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from .base import Skill


class RunScriptInput(BaseModel):
    script_name: str = Field(description="Name of the Python script to run")


class RunnerSkill(Skill):
    """Provides the run_script tool."""

    def get_tools(self):
        work_dir = self.archive.work_dir
        archive = self.archive
        timeout = self.config.script_timeout

        async def run_script_tool(script_name: str) -> str:
            script_path = work_dir / script_name
            if not script_path.exists():
                return f"ERROR: Script '{script_name}' not found"

            print(f"\nRunning {script_name}...", flush=True)
            try:
                result = subprocess.run(
                    ["python", script_name],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode == 0:
                    print("Script ran successfully", flush=True)
                    return f"SUCCESS\nOutput:\n{result.stdout[:500]}"
                else:
                    error_msg = (
                        f"Return code {result.returncode}\n"
                        f"Stderr: {result.stderr}\n"
                        f"Stdout: {result.stdout}"
                    )
                    print(f"Failed (code {result.returncode})", flush=True)
                    archive.archive_run_output(error_msg)
                    return (
                        f"FAILED (code {result.returncode})\n"
                        f"Stderr:\n{result.stderr}\n"
                        f"Stdout:\n{result.stdout[:500]}"
                    )
            except subprocess.TimeoutExpired:
                return f"ERROR: Script timed out ({timeout}s)"
            except Exception as e:
                return f"ERROR: {e}"

        return [
            StructuredTool(
                name="run_script",
                description="Run a Python script. Returns SUCCESS or FAILED with error details.",
                args_schema=RunScriptInput,
                coroutine=run_script_tool,
            ),
        ]
