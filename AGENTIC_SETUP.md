# Running libEnsemble agentic workflows

For all workflows, you will need a key to access an LLM.

For example, you can set an OpenAPI key. 
Requires an [OpenAI account](https://platform.openai.com).
Make sure to check MODEL at top of agentic script and usage rates.

Set user OpenAI API Key:

```bash
export OPENAI_API_KEY="sk-your-key-here"
```

Or if you use Anthropic, you can set.

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

Optionally, you can set the `LLM_MODEL` env variable to a model name.

<details>
<summary>Using Argonne inference service (optional)</summary>

If you have an ALCF account, you can use Argonne inference service instead of OpenAI.

Authenticate via Globus to obtain ALCF inference token:

```bash
pip install openai globus_sdk
wget https://raw.githubusercontent.com/argonne-lcf/inference-endpoints/main/inference_auth_token.py
python inference_auth_token.py authenticate  # Enter globus authentication when prompted.
```

Set environment variables for ALCF Inference service and model. Obtain API Key:

```bash
export OPENAI_BASE_URL=https://inference-api.alcf.anl.gov/resource_server/metis/api/v1
export LLM_MODEL=gpt-oss-120b
export OPENAI_API_KEY=$(python inference_auth_token.py get_access_token)
```

</details>


## libe_agent_basic.py

Agent for running libEnsemble scripts with error recovery.

Requires:

```bash
pip install libensemble scipy mpmath langchain langchain-openai
```

### Running

```bash
git clone https://github.com/Libensemble/script-creator.git
cd script-creator/agentic/
```

To run:

Provide path to directory with your libEnsemble scripts. These will be copied 
to a working directory `generated_scripts/`.

```bash
python libe_agent_basic.py --scripts tests/scripts_with_errors/
```

To see script fixes:

```bash
cd generated_scripts/versions/
diff 1_copied_scripts/run_example.py 2_fix_attempt_1/run_example.py
```

This basic agentic script is sufficiently general that it should work with
any Python workflow, not just libEnsemble. Any Python scripts in the
input directory will be presented to the AI in the case of error. The default
run script should be of the form `run_*.py`.

Alternatively you can run through the [web interface](agentic/web_ui/README.md) (locally).


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
