# Using the MCP Tool in Cursor IDE

This repository includes an MCP (Model Context Protocol) server that allows you to generate libEnsemble scripts directly from Cursor IDE (or any MCP client) using AI assistance.

This enables an AI to call the script creator providing fields it has inferred from your 
discussion.

## Prerequisites

Node.js is required to run the MCP server. For Example.

**Linux (Ubuntu/Debian):**
```bash
sudo apt install nodejs
```

**Other platforms:** Download and install from https://nodejs.org/

## Quick Setup

### 1. Clone This Repository and Install Dependencies

```bash
git clone https://github.com/Libensemble/script-creator.git
cd script-creator
npm install
```

### 2. Configure Cursor

Create or edit `~/.cursor/mcp.json` and add the path to the `mcp_server.mjs` file:

```json
{
  "mcpServers": {
    "script-creator": {
      "command": "node",
      "args": ["</absolute/path/to/script-creator>/mcp_server.mjs"]
    }
  }
}
```

**Important:** Replace `/absolute/path/to/script-creator/` with the path from the `pwd` command above.

### 3. Restart Cursor

Close and reopen Cursor IDE. The MCP server will start automatically.

## Usage

Once set up, you can ask Cursor's AI assistant to "create libEnsemble scripts" with your parameters. For example:

- "Create libEnsemble scripts using APOSMM generator optimizing two parameters. The executable is /my/path/test.x and the input file is input.txt. The variables to alter in that file are called dim_x and dim_y. They both have upper and lower bounds of -1 to 1. Create the scripts is a sub-directory called my_run."

The AI will use the `CreateLibEnsembleScripts` tool to generate libEnsemble scripts including `run_libe.py` and `simf.py`.

## Troubleshooting

- **Tool not appearing?** Check that the path in `mcp.json` is absolute and correct
- **Server errors?** Make sure you ran `npm install` to install dependencies
- **Still not working?** Go to Cursor Setting and section Tools and MCP for error messages

## Files

- `mcp_server.mjs` - The MCP server implementation - in the script_creator root directory.
- `package.json` - Node.js dependencies (includes `@modelcontextprotocol/sdk` and `mustache`)
