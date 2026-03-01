"""Agent orchestrator — builds the agent, runs autonomous or interactive mode."""

import shutil
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from .archive import ArchiveManager
from .config import AgentConfig, INPUT_MARKER
from .llm import create_llm
from .mcp_client import connect_mcp, find_mcp_server
from .prompts import (
    AUTONOMOUS_GOAL,
    INTERACTIVE_GOAL,
    INTERACTIVE_REVIEW_GOAL,
    build_system_prompt,
)
from .scripts import detect_run_script
from .skills import load_skills
from .skills.generator import GeneratorSkill


async def run_agent(config: AgentConfig):
    """Main entry point: build skills, connect MCP, run the agent loop."""

    # Archive existing output dir before starting fresh
    ArchiveManager.archive_existing_output_dir(config.output_dir)

    # Set up archive manager
    archive = ArchiveManager(config.output_dir)

    # Load skills — drop generator when using existing scripts
    skill_names = config.skills
    if config.scripts_dir and "generator" in skill_names:
        skill_names = ",".join(s for s in skill_names.split(",") if s.strip() != "generator")
    skills = load_skills(skill_names, config, archive)
    has_generator = any(isinstance(s, GeneratorSkill) for s in skills)

    # MCP setup for generator skill
    async with AsyncExitStack() as stack:
        if has_generator:
            mcp_server = find_mcp_server(config.mcp_server)
            print(f"Generator MCP: {mcp_server}")
            session = await stack.enter_async_context(connect_mcp(mcp_server))
            print("Connected to MCP server")

            # Get MCP tool schema and inject into generator skill
            mcp_tools = await session.list_tools()
            mcp_tool = mcp_tools.tools[0]
            for skill in skills:
                if isinstance(skill, GeneratorSkill):
                    skill.set_mcp_session(session)
                    skill.set_mcp_tool_schema(mcp_tool)

        # Collect tools from all skills
        tools = []
        for skill in skills:
            tools.extend(skill.get_tools())

        # Create LLM and agent
        llm, service = create_llm(config.model, config.temperature, config.base_url)
        agent = create_agent(llm, tools)
        print(f"Agent initialized (model: {config.model}, service: {service})\n")

        # Build system prompt
        system_prompt = build_system_prompt(skills, has_generator)
        messages = [("system", system_prompt)]

        if config.show_prompts:
            print(f"System prompt:\n{system_prompt}\n")

        # Determine initial message
        initial_msg = _build_initial_message(config, archive)

        if not config.interactive:
            await _run_autonomous(agent, messages, initial_msg, config)
        else:
            await _run_interactive(agent, messages, initial_msg, config, has_generator)


def _build_initial_message(config, archive):
    """Build the first user message based on config."""
    if config.scripts_dir:
        scripts_dir = Path(config.scripts_dir)
        for f in sorted(scripts_dir.glob("*.py")):
            shutil.copy(f, archive.work_dir)
            print(f"Copied: {f.name}")
        archive.start("copied_scripts")
        archive.archive_scripts()

        run_scripts = list(archive.work_dir.glob("run_*.py"))
        run_name = run_scripts[0].name if run_scripts else "run_libe.py"
        return INTERACTIVE_REVIEW_GOAL.format(run_script_name=run_name)

    user_prompt = config.get_user_prompt()
    if user_prompt:
        return user_prompt

    if config.interactive:
        print("Describe the scripts you want to generate (or press Enter for default demo):", flush=True)
        print(INPUT_MARKER, flush=True)
        user_input = input().strip()
        if user_input:
            return user_input
        print("Using default demo prompt")

    return (
        "Create six_hump_camel APOSMM scripts:\n"
        "- Executable: six_hump_camel/six_hump_camel.x\n"
        "- Input: six_hump_camel/input.txt\n"
        "- Template vars: X0, X1\n"
        "- 4 workers, 100 sims.\n"
        "- The output file for each simulation is output.txt\n"
        "- The bounds should be 0,1 and -1,2 for X0 and X1 respectively"
    )


async def _run_autonomous(agent, messages, initial_msg, config):
    """Single invocation — agent generates/loads, runs, fixes, reports."""
    goal = AUTONOMOUS_GOAL.format(initial_msg=initial_msg)
    messages.append(("user", goal))

    if config.show_prompts:
        print(f"Goal: {goal}\n")
    print("Starting agent...\n")

    result = await agent.ainvoke({"messages": messages})
    print(f"\n{'=' * 60}")
    print("Agent completed")
    print(f"{'=' * 60}")
    content = result["messages"][-1].content
    if isinstance(content, list):
        content = "".join(block.get("text", "") for block in content)
    print(content)


async def _run_interactive(agent, messages, initial_msg, config, has_generator):
    """Chat loop — agent responds, waits for user input, repeats."""
    if has_generator:
        goal = INTERACTIVE_GOAL.format(initial_msg=initial_msg)
    else:
        goal = initial_msg
    messages.append(("user", goal))
    print("Starting agent...\n")

    while True:
        try:
            result = await agent.ainvoke({"messages": messages})
            messages = result["messages"]
            response = messages[-1].content
            if isinstance(response, list):
                response = "".join(block.get("text", "") for block in response)
            if response:
                print(f"\n{response}", flush=True)
        except Exception as e:
            print(f"\nAgent error: {e}", flush=True)

        # Wait for user input
        print(INPUT_MARKER, flush=True)
        user_input = input().strip()

        if not user_input or user_input.lower() in ("quit", "exit", "done"):
            print("\nSession ended")
            break

        messages.append(
            SystemMessage(
                content="STOP. Read the user's next message carefully and respond to exactly what they ask. "
                "Do not continue previous tasks."
            )
        )
        messages.append(HumanMessage(content=user_input))
