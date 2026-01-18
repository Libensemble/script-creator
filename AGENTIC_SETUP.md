# Setup

## Prerequisites

**libEnsemble**

```bash
pip install libensemble
```

**Node.js** - Required for MCP server (not needed if using --scripts option)

```bash
# Linux (Ubuntu/Debian)
sudo apt install nodejs

# Or download from https://nodejs.org/
```

Install Node.js dependencies:

```bash
npm install
```

## Install Python Dependencies

```bash
pip install langchain langchain-openai mcp openai
```

## Set OpenAI API Key

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

Add to `~/.bashrc` or `~/.zshrc` to persist.

## Run

```bash
# Use default prompt
python agentic_langchain_mcp.py

# Custom prompt
python agentic_langchain_mcp.py "Create my_app APOSMM scripts..."

# Use existing scripts (skip MCP generation/tweaking)
python agentic_langchain_mcp.py --scripts example_scripts/
```

Scripts saved to `generated_scripts/` directory.

Scripts will be ran, fixes attempted on failure, and reran.
