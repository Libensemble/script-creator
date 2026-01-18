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
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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
    print("Updating scripts...")
    
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

def save_scripts(scripts_text, output_dir):
    """Save generated scripts to files"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    pattern = r"=== (.+?) ===\n(.*?)(?=\n===|$)"
    matches = re.findall(pattern, scripts_text, re.DOTALL)
    
    for filename, content in matches:
        filepath = output_dir / filename.strip()
        filepath.write_text(content.strip() + "\n")
        print(f"Saved: {filepath}")

def run_generated_scripts(output_dir):
    """Stage 3: Run the generated scripts"""
    print("\nRunning scripts...")
    
    output_dir = Path(output_dir)
    run_script = output_dir / "run_libe.py"
    
    if not run_script.exists():
        print("Error: run_libe.py not found")
        return False
    
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
        return True
    else:
        print(f"✗ Scripts failed with return code {result.returncode}")
        if result.stderr:
            print(f"Error output:\n{result.stderr[:500]}")
        return False

async def main():
    global mcp_session
    
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
            
            # Get user prompt from command line or use default
            user_prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT
            
            # Stage 1: Run MCP generator
            scripts_text = await run_mcp_generator(agent, user_prompt)
            if not scripts_text:
                print("No scripts generated")
                return
            
            # Stage 2: Update scripts
            final_scripts = await update_scripts(agent, scripts_text, user_prompt)
            
            # Save scripts
            output_dir = "generated_scripts"
            save_scripts(final_scripts, output_dir)
            
            # Stage 3: Run scripts
            run_generated_scripts(output_dir)

if __name__ == "__main__":
    asyncio.run(main())
