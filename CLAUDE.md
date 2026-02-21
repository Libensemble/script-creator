# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **libEnsemble Script Creator** — a system for generating, running, and iteratively fixing [libEnsemble](https://libensemble.readthedocs.io/) scripts (used for parallel optimization at HPC centers). It has three deployment modes:

1. **MCP Server** (`mcp_server.mjs`) — Node.js server exposing script generation as an MCP tool (used from Cursor IDE or AI agents)
2. **Agentic Python scripts** (`agentic/`) — LangChain agents that generate scripts via MCP, run them, and auto-fix errors
3. **Web UI** (`web/`) — Flask backend + HTML/JS frontend for interactive script refinement

## Key Commands

### MCP Server (Node.js)
```bash
npm install          # Install dependencies
node mcp_server.mjs  # Run MCP server
```

### Agentic Agents (Python)

Install dependencies:
```bash
pip install langchain langchain-openai mcp openai libensemble scipy mpmath
```

Run the primary agent (generate → run → fix):
```bash
cd agentic/
python libe_agent_with_script_generator.py             # Uses DEFAULT_PROMPT
python libe_agent_with_script_generator.py "Create APOSMM scripts..."
python libe_agent_with_script_generator.py --prompt-file my_prompt.txt
python libe_agent_with_script_generator.py --scripts example_scripts/  # Skip generation
python libe_agent_with_script_generator.py --show-prompts               # Debug prompts
```

Run the interactive agent (with user chat loop + RAG doc lookup):
```bash
# Extra deps for RAG:
pip install llama-index llama-index-embeddings-huggingface sentence-transformers

export GENERATOR_MCP_SERVER=/path/to/mcp_server.mjs
export RAG_MCP_SERVER=/path/to/rag/mcp_server.py
export OPENAI_API_KEY=your_key

python libe_agent_interactive_with_rag.py --interactive
python libe_agent_interactive_with_rag.py --generate-only  # No execution
python libe_agent_interactive_with_rag.py --scripts dir/   # Review existing
```

### Web Interface
```bash
cd web/
pip install -r requirements.txt
export OPENAI_API_KEY=your_key
python server.py   # Serves on http://localhost:5000
```

### RAG System
```bash
cd rag/
pip install llama-index llama-index-embeddings-huggingface sentence-transformers mcp
python build_index.py   # Build vector index from libEnsemble docs (run once)
python rag_query.py "What generators are available?"
python test_mcp_server.py  # Test the RAG MCP server
```

## Architecture

### Script Generation Pipeline
The MCP server (`mcp_server.mjs`) uses **Mustache templates** (`templates/*.j2` — despite the `.j2` extension, rendered by Mustache in Node.js) and `processTemplateData.js` (shared browser/Node logic) to produce:
- `run_libe.py` — main libEnsemble runner
- `simf.py` — simulation function
- `submit_slurm.sh` / `submit_pbs.sh` — HPC job scripts

Generator configurations are data-driven via `data/generators.json` and `data/generator_specs.json`.

### Agent Workflow
```
User prompt
    → LangChain agent calls MCP tool CreateLibEnsembleScripts
    → Agent refines scripts (second LLM pass)
    → Agent runs scripts via subprocess
    → On failure: optionally queries RAG for doc context, then fixes and reruns
    → All versions saved to generated_scripts/versions/
```

Key constants in agents:
- `MAX_RETRIES = 2` — retry attempts on script failure
- `LLM_MODEL` env var (default: `gpt-4o-mini`) — overrides model for all agents

### MCP Protocol Usage
Agents connect to MCP servers via `stdio_client` (the MCP Python SDK). There are two MCP servers:
1. `mcp_server.mjs` — exposes `CreateLibEnsembleScripts` tool
2. `rag/mcp_server.py` — exposes `query_libe_docs`, `query_generator_docs`, etc.

### Environment Variables
```
OPENAI_API_KEY        # Required for agents
OPENAI_BASE_URL       # Optional: alternative LLM endpoint (e.g., ALCF inference)
LLM_MODEL             # Optional: model name (default: gpt-4o-mini)
MCP_SERVER            # Path to mcp_server.mjs (used by agents)
GENERATOR_MCP_SERVER  # Path to generator MCP server
RAG_MCP_SERVER        # Path to rag/mcp_server.py
```

### Testing
No automated test suite. Manual testing uses:
- `agentic/tests/` — test scripts with intentional errors (filename errors, wrong paths, missing try/except, etc.)
- The six_hump_camel benchmark problem in `six_hump_camel/` as a reference optimization case

To test an agent against a known-error script:
```bash
python libe_agent_with_script_generator.py --scripts agentic/tests/scripts_with_errors/
```
