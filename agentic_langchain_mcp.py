#!/usr/bin/env python3
"""
LangChain agent for MCP script-creator tool
Requirements: pip installlangchain langchain-openai mcp openai

Runs the script generator MCP tool.
Performs a second pass to tweak the script.
Runs the scripts and reports if successful.
"""

import os
import sys
import asyncio
import re
import subprocess
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Maximum retry attempts for fixing failed scripts
MAX_RETRIES = 1

# Default prompt if none provided
DEFAULT_PROMPT = """Create six_hump_camel APOSMM scripts:
- Executable: /home/shudson/test_mcp/script-creator/six_hump_camel/six_hump_camel.x
- Input: /home/shudson/test_mcp/script-creator/six_hump_camel/input.txt
- Template vars: X0, X1
- 4 workers, 100 sims.
- The output file for each simulation is output.txt
- The bounds should be 0,1 and -1,2 for X0 and X1 respectively"""

# Template for second-pass refinement
REFINE_PROMPT_TEMPLATE = """Here are the generated scripts:

{scripts_text}

Review the scripts against the requirements in: {user_prompt}

Only modify if the user prompt specifies something clearly different from what is currently in the scripts.
Modifications should only be to configuration values, bounds, parameters, and options within the existing code structure.
Do NOT add new variables, functions, or executable code outside the existing structure.

CRITICAL OUTPUT REQUIREMENTS:
- Return ONLY the scripts in the format shown above (=== filename === followed by code)
- Do NOT add explanations, comments about changes, or any text outside the code
- Do NOT wrap in markdown
- The output must be EXACTLY like the input format - parseable code only"""

# Global MCP session
mcp_session = None

async def call_mcp_tool(**kwargs):
    """Wrapper to call the MCP tool"""
    # Block custom_set_objective - AI always gets it wrong
    if 'custom_set_objective' in kwargs:
        del kwargs['custom_set_objective']
    if 'set_objective_code' in kwargs:
        del kwargs['set_objective_code']
    
    result = await mcp_session.call_tool("CreateLibEnsembleScripts", kwargs)
    return result.content[0].text if result.content else "Scripts created"

async def run_mcp_generator(agent, user_prompt):
    """Stage 1: Run the MCP script generator"""
    print("Running MCP script generator...")
    
    result = await agent.ainvoke({
        "messages": [("user", user_prompt)]
    })
    
    # Find the tool result (MCP-generated scripts)
    for msg in result["messages"]:
        if hasattr(msg, "type") and msg.type == "tool":
            return msg.content
    
    return None

async def update_scripts(agent, scripts_text, user_prompt):
    """Stage 2: Update scripts based on user requirements"""
    print("Updating script details...")
    
    refine_prompt = REFINE_PROMPT_TEMPLATE.format(
        scripts_text=scripts_text,
        user_prompt=user_prompt
    )
    
    refine_result = await agent.ainvoke({
        "messages": [("user", refine_prompt)]
    })
    
    # Get the refined scripts from AI response
    final_scripts = refine_result["messages"][-1].content
    
    # Strip markdown code fences if present
    final_scripts = re.sub(r'```python\n', '', final_scripts)
    final_scripts = re.sub(r'```\n?', '', final_scripts)
    
    # Strip any explanatory text before/after the scripts
    if '===' in final_scripts:
        start = final_scripts.find('===')
        final_scripts = final_scripts[start:]
    
    return final_scripts

def save_scripts(scripts_text, output_dir, archive_name=None):
    """Save generated scripts to files and optionally archive"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    pattern = r"=== (.+?) ===\n(.*?)(?=\n===|$)"
    matches = re.findall(pattern, scripts_text, re.DOTALL)
    
    for filename, content in matches:
        filepath = output_dir / filename.strip()
        filepath.write_text(content.strip() + "\n")
        print(f"Saved: {filepath}")
    
    # Archive this version if requested
    if archive_name:
        archive_dir = output_dir / "versions" / archive_name
        archive_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in matches:
            archive_path = archive_dir / filename.strip()
            archive_path.write_text(content.strip() + "\n")

def copy_existing_scripts(scripts_dir, output_dir):
    """Copy scripts from existing directory and return as formatted text"""
    print(f"Using existing scripts from: {scripts_dir}")
    scripts_dir = Path(scripts_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    scripts_text = ""
    for script_file in scripts_dir.glob("*.py"):
        shutil.copy(script_file, output_dir)
        print(f"Copied: {script_file.name}")
        scripts_text += f"=== {script_file.name} ===\n{script_file.read_text()}\n\n"
    
    return scripts_text

def run_generated_scripts(output_dir):
    """Stage 3: Run the generated scripts"""
    print("\nRunning scripts...")
    
    output_dir = Path(output_dir)
    run_script = output_dir / "run_libe.py"
    
    if not run_script.exists():
        print("Error: run_libe.py not found")
        return False, "run_libe.py not found"
    
    # Run the script and capture output
    result = subprocess.run(
        ["python", "run_libe.py"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=300  # 5 minute timeout
    )
    
    # Check if successful
    if result.returncode == 0:
        print("✓ Scripts ran successfully")
        return True, None
    else:
        error_msg = f"Return code {result.returncode}\nStderr: {result.stderr}\nStdout: {result.stdout}"
        print(f"✗ Scripts failed with return code {result.returncode}")
        if result.stderr:
            print(f"Error output:\n{result.stderr[:500]}")
        return False, error_msg

async def fix_scripts(agent, scripts_text, error_msg):
    """Fix scripts based on error message"""
    print("Attempting to fix scripts based on error...")
    
    fix_prompt = f"""These scripts failed with the following error:

{error_msg}

Here are the current scripts:

{scripts_text}

Fix the scripts to resolve this error.
Return ALL scripts in the EXACT SAME FORMAT (=== filename === followed by raw Python code).
DO NOT wrap in markdown or add explanations."""
    
    fix_result = await agent.ainvoke({
        "messages": [("user", fix_prompt)]
    })
    
    fixed_scripts = fix_result["messages"][-1].content
    
    # Clean up
    fixed_scripts = re.sub(r'```python\n', '', fixed_scripts)
    fixed_scripts = re.sub(r'```\n?', '', fixed_scripts)
    if '===' in fixed_scripts:
        start = fixed_scripts.find('===')
        fixed_scripts = fixed_scripts[start:]
    
    return fixed_scripts

async def main():
    global mcp_session
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Generate and run libEnsemble scripts")
    parser.add_argument("--scripts", help="Use existing scripts from directory (skip generation)")
    parser.add_argument("--prompt", help="Prompt for script generation (default: use DEFAULT_PROMPT)")
    args = parser.parse_args()
    
    output_dir = "generated_scripts"
    
    # Copy existing scripts if provided
    archive_counter = 1
    if args.scripts:
        current_scripts = copy_existing_scripts(args.scripts, output_dir)
        skip_generation = True
    else:
        skip_generation = False
    
    # Connect to MCP server
    server_params = StdioServerParameters(command="node", args=["mcp_server.mjs"])
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_session = session
            
            # Get MCP tool schema with enums
            mcp_tools = await session.list_tools()
            mcp_tool = mcp_tools.tools[0]  # CreateLibEnsembleScripts
            
            # Create LangChain tool from MCP schema
            lc_tool = StructuredTool(
                name=mcp_tool.name,
                description=mcp_tool.description,
                args_schema=mcp_tool.inputSchema,  # This includes enum constraints
                coroutine=call_mcp_tool
            )
            
            # Create LangChain agent
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            agent = create_agent(llm, [lc_tool])
            
            # Stage 1: Run MCP generator
            if not skip_generation:
                user_prompt = args.prompt or DEFAULT_PROMPT
                scripts_text = await run_mcp_generator(agent, user_prompt)
                if not scripts_text:
                    print("No scripts generated")
                    return
                
                # Archive initial MCP output
                save_scripts(scripts_text, output_dir, archive_name=f"{archive_counter}_mcp_output")
                archive_counter += 1
            else:
                scripts_text = current_scripts
            
            # Stage 2: Update scripts
            if not skip_generation:
                user_prompt = args.prompt or DEFAULT_PROMPT
                current_scripts = await update_scripts(agent, scripts_text, user_prompt)
                
                # Save and archive updated scripts
                save_scripts(current_scripts, output_dir, archive_name=f"{archive_counter}_after_update")
                archive_counter += 1
            else:
                # Save and archive copied scripts before retry loop
                save_scripts(current_scripts, output_dir, archive_name=f"{archive_counter}_copied_scripts")
                archive_counter += 1
            
            # Stage 3: Run scripts with retry loop
            for attempt in range(MAX_RETRIES + 1):
                success, error_msg = run_generated_scripts(output_dir)
                
                if success:
                    break
                
                if attempt < MAX_RETRIES:
                    print(f"\nRetry attempt {attempt + 1}/{MAX_RETRIES}")
                    current_scripts = await fix_scripts(agent, current_scripts, error_msg)
                    save_scripts(current_scripts, output_dir, archive_name=f"{archive_counter}_fix_attempt_{attempt + 1}")
                    archive_counter += 1
                else:
                    print(f"\nFailed after {MAX_RETRIES} retry attempts")

if __name__ == "__main__":
    asyncio.run(main())
