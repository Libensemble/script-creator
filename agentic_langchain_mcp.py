#!/usr/bin/env python3
"""
LangChain agent for MCP script-creator tool
Requirements: pip install langchain-openai mcp
"""

import os
import sys
import asyncio
import re
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Current this just runs the MCP tool iteration.
# To do - add a pass to add any user defined bounds and other details.

# Default prompt if none provided
DEFAULT_PROMPT = """Create six_hump_camel APOSMM scripts:
- Executable: /home/shudson/test_mcp/script-creator/six_hump_camel/six_hump_camel.x
- Input: /home/shudson/test_mcp/script-creator/six_hump_camel/input.txt
- Template vars: X0, X1
- 4 workers, 100 sims.
- The output file for each simulation is output.txt"""

# Global MCP session
mcp_session = None

async def call_mcp_tool(**kwargs):
    """Wrapper to call the MCP tool"""
    result = await mcp_session.call_tool("CreateLibEnsembleScripts", kwargs)
    return result.content[0].text if result.content else "Scripts created"

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
            
            # Run
            result = await agent.ainvoke({
                "messages": [("user", user_prompt)]
            })
            
            # Find the tool result and save scripts
            for msg in result["messages"]:
                if hasattr(msg, "type") and msg.type == "tool":
                    scripts_text = msg.content
                    
                    # Default output directory
                    output_dir = Path("generated_scripts")
                    output_dir.mkdir(exist_ok=True)
                    
                    # Parse and save each script file
                    pattern = r"=== (.+?) ===\n(.*?)(?=\n===|$)"
                    matches = re.findall(pattern, scripts_text, re.DOTALL)
                    
                    for filename, content in matches:
                        filepath = output_dir / filename.strip()
                        filepath.write_text(content.strip() + "\n")
                        print(f"Saved: {filepath}")
                    
                    break

if __name__ == "__main__":
    asyncio.run(main())
