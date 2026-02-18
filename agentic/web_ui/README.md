# Web UI for libEnsemble Agents

Web interface for running libEnsemble agent scripts with real-time output and script viewing.

## Installation

Install the required dependencies:

```bash
pip install fastapi uvicorn[standard] gradio websockets
```

## Usage

The web UI consists of two components that need to run simultaneously:

### 1. Start the WebSocket Server (Terminal 1)

Run the FastAPI backend server (from web_ui dir):

```bash
uvicorn app:app --reload --port 8000
```

This starts the WebSocket server on `ws://127.0.0.1:8000`.

### 2. Start the Gradio UI (Terminal 2)

In a separate terminal, run the Gradio interface:

```bash
python gradio_chat.py
```

This will launch the web interface (typically at `http://127.0.0.1:7860`).

### 3. Use the Web Interface

1. **Select Agent Script**: Choose which agent script to run (e.g., `libe_agent_basic.py`)
2. **Select Scripts Directory**: Choose the test directory containing scripts to process
3. **Click Run**: The agent will execute and output will appear in real-time
4. **View Generated Scripts**: Generated scripts will appear in the dropdown and can be viewed

## Directory Structure

- `app.py` - FastAPI WebSocket server backend
- `gradio_chat.py` - Gradio web interface frontend
- Agent scripts should be in `agentic/` directory (parent of `web_ui/`)
- Test script directories should be in `agentic/tests/`
