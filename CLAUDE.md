# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **libEnsemble Script Creator** — a system for generating [libEnsemble](https://libensemble.readthedocs.io/) scripts (used for parallel optimization at HPC centers). It has two deployment modes:

1. **MCP Server** (`mcp_server.mjs`) — Node.js server exposing script generation as an MCP tool (used from Cursor IDE or AI agents)
2. **Web UI** (`web/`) — Flask backend + HTML/JS frontend for interactive script refinement

## Key Commands

### MCP Server (Node.js)
```bash
npm install          # Install dependencies
node mcp_server.mjs  # Run MCP server
```

### Web Interface
```bash
cd web/
pip install -r requirements.txt
export OPENAI_API_KEY=your_key
python server.py   # Serves on http://localhost:5000
```

## Architecture

### Script Generation Pipeline
The MCP server (`mcp_server.mjs`) uses **Mustache templates** (`templates/*.j2` — despite the `.j2` extension, rendered by Mustache in Node.js) and `processTemplateData.js` (shared browser/Node logic) to produce:
- `run_libe.py` — main libEnsemble runner
- `simf.py` — simulation function
- `submit_slurm.sh` / `submit_pbs.sh` — HPC job scripts

Generator configurations are data-driven via `data/generators.json` and `data/generator_specs.json`.

### MCP Tool
The MCP server exposes the `CreateLibEnsembleScripts` tool.

### Testing
No automated test suite. The six_hump_camel benchmark problem in `six_hump_camel/` serves as a reference optimization case.
