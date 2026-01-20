# Running libEnsemble agentic workflows

For all workflows, you will need an OpenAPI key. 
Requires an [OpenAI account](https://platform.openai.com).
Make sure to check MODEL at top of agentic script and usage rates.

Option to run with a local model will be added soon.

Set user OpenAI API Key:

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

## libe_agent_basic.py

Agent for running libEnsemble scripts with error recovery.

Requires:

```bash
pip install libensemble langchain langchain-openai
```

### Running

```bash
cd agentic/
```

To run:

Provide path to directory with your libEnsemble scripts. These will be copied 
to a working directory `generated_scripts/`.

```bash
python libe_agent_basic.py --scripts tests/scripts_with_errors/
```

This basic agentic script is sufficiently general that it should work with
any Python workflow, not just libEnsemble. Any Python scripts in the
input directory will be presented to the AI in the case of error. The default
run script should be of the form `run_*.py`.


## Running scripts with a binary

To run test scripts_with_exe_with_errors/ , build **six_hump_camel.x**:

```bash
cd tests/six_hump_camel/
gcc six_hump_camel.c -o six_hump_camel.x -lm
cd ../..
```
and update paths to `sim_app` and `input_file` in `tests/scripts_with_errors/run_example.py`.
*Missing file paths are not yet corrected automatically*.

To run:

Provide path to directory with your libEnsemble scripts. These will be copied 
to a working directory `generated_scripts/`.

```bash
python libe_agent_basic.py --scripts tests/scripts_with_exe_with_errors/
```

## libe_agent_with_script_generator.py

Agent for libEnsemble scripts with error recovery, including optional use of
the script generator MCP tool.

Requires:

```bash
pip install libensemble langchain langchain-openai mcp
```

**Node.js** - Required for MCP server.

```bash
# Linux (Ubuntu/Debian)
sudo apt install nodejs

# Or download from https://nodejs.org/
```

Install Node.js dependencies:

```bash
npm install
```

Requires this repository to be cloned to access the MCP tool. The file
`mcp_server.mjs` should not be moved from it's original location. This
file will be found if you run in the same directory or one below. To run
the script elsewhere, use the `--mcp-server` command line option to point
to this file.

### Running

```bash

cd agentic/

# Use default prompt
python libe_agent_with_script_generator.py

# Custom prompt
python libe_agent_with_script_generator.py "Create my_app APOSMM scripts..."

# Custom prompt in a file
python libe_agent_with_script_generator.py --prompt-file my_prompt.txt

# Use existing scripts (skip MCP generation/tweaking)
python libe_agent_with_script_generator.py --scripts example_scripts/

# Run from anywhere 
python libe_agent_with_script_generator.py --mcp-server <path/to/mcp_server.mjs>
```
Scripts saved to `generated_scripts/` directory.

Scripts will be ran, fixes attempted on failure, and reran.
