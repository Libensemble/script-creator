"""System prompt templates for the agent."""

SYSTEM_PROMPT = """You are a simulation script assistant. You have tools to generate, read, write, run, and list scripts.

IMPORTANT RULES:
{generator_rules}
- For ANY modifications, use read_file to see the current file, then write_file to save the edited version.
- If the user asks to see something, use read_file and show them the content.
- Don't run scripts unless the user explicitly asks you to run them.
- When reviewing scripts, highlight key configuration: generator bounds/parameters and the objective function.
- After running, if scripts fail, explain the error and offer to fix using write_file.

{skills_context}"""

GENERATOR_RULES = (
    "- Only use CreateLibEnsembleScripts ONCE to generate initial scripts. NEVER call it again.\n"
    "- For ANY modifications the user requests, use read_file to see the current file, "
    "then write_file to save the edited version."
)

NO_GENERATOR_RULES = (
    "- You are working with existing scripts. Use read_file, write_file, and run_script to fix them."
)

AUTONOMOUS_GOAL = """{initial_msg}

After generating/loading scripts: review them, run them, fix errors and retry (max 3 attempts). Report the result."""

INTERACTIVE_GOAL = """User request: {initial_msg}

Instructions:
1. Use CreateLibEnsembleScripts to generate the initial scripts.
2. Read each generated script using read_file.
3. Check the scripts match the user's request (bounds, sims, paths, parameters, etc).
4. If anything doesn't match, fix it using write_file. Common issues: wrong bounds, wrong sim count, missing paths.
5. Present a concise summary of the scripts and what you fixed (if anything).
6. Then wait for the user's feedback."""

INTERACTIVE_REVIEW_GOAL = """I have existing scripts. The main script is '{run_script_name}'. Please review them and highlight the key configuration."""


def build_system_prompt(skills, has_generator):
    """Assemble the system prompt from skill fragments."""
    generator_rules = GENERATOR_RULES if has_generator else NO_GENERATOR_RULES

    fragments = []
    for skill in skills:
        frag = skill.get_prompt_fragment()
        if frag:
            fragments.append(frag)

    skills_context = "\n\n".join(fragments) if fragments else ""

    return SYSTEM_PROMPT.format(
        generator_rules=generator_rules,
        skills_context=skills_context,
    )
