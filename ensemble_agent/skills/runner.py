"""Script runner skill — execute scripts with timeout and archive output."""

import subprocess

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from .base import Skill
from ..config import MAX_RETRIES


class RunScriptInput(BaseModel):
    script_name: str = Field(description="Name of the Python script to run")


class RunnerSkill(Skill):
    """Provides the run_script tool."""

    def __init__(self, config, archive):
        super().__init__(config, archive)
        self._run_count = 0
        self._max_runs = config.max_retries + 1  # initial run + retries

    def get_tools(self):
        work_dir = self.archive.work_dir
        archive = self.archive
        timeout = self.config.script_timeout
        skill = self

        async def run_script_tool(script_name: str) -> str:
            skill._run_count += 1
            if skill._run_count > skill._max_runs:
                msg = f"RUN LIMIT REACHED ({skill._max_runs} runs). Stop and report the current status to the user."
                print(f"\n{msg}", flush=True)
                return msg

            script_path = work_dir / script_name
            if not script_path.exists():
                return f"ERROR: Script '{script_name}' not found"

            print(f"\nRunning {script_name}... (run {skill._run_count}/{skill._max_runs})", flush=True)
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
                    remaining = skill._max_runs - skill._run_count
                    return (
                        f"FAILED (code {result.returncode})\n"
                        f"Stderr:\n{result.stderr}\n"
                        f"Stdout:\n{result.stdout[:500]}\n"
                        f"\nYou have {remaining} run(s) remaining."
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
