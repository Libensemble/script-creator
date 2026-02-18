import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Queue, Empty

import gradio as gr
import websockets

WS_URL = "ws://127.0.0.1:8000/ws/test"
AGENT_DIR = Path(__file__).parent.parent
TESTS_DIR = AGENT_DIR / "tests"

ws_conn = None
message_queue = Queue()
output_queue = Queue()
ws_thread = None
stop_event = threading.Event()
uvicorn_process = None


def scan_agent_scripts():
    exclude = {"app.py", "gradio_chat.py", "__init__.py"}
    return [f.name for f in sorted(AGENT_DIR.glob("*.py")) if f.name not in exclude]


def scan_script_dirs():
    if not TESTS_DIR.exists():
        return []
    return [d.name for d in sorted(TESTS_DIR.iterdir()) if d.is_dir() and not d.name.startswith("_")]




def websocket_worker():
    global ws_conn
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        global ws_conn
        try:
            ws_conn = await websockets.connect(WS_URL)
            output_queue.put(("message", json.dumps({"type": "log", "text": "Connected to websocket"})))
            while not stop_event.is_set():
                try:
                    msg_to_send = message_queue.get_nowait()
                    await ws_conn.send(msg_to_send)
                except Empty:
                    pass
                try:
                    raw = await asyncio.wait_for(ws_conn.recv(), timeout=0.1)
                    output_queue.put(("message", raw))
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    output_queue.put(("error", "Websocket connection closed"))
                    break
            if ws_conn:
                await ws_conn.close()
        except Exception as e:
            error_msg = f"Websocket error: {str(e)}"
            print(error_msg)  # Also print to console
            output_queue.put(("error", error_msg))

    loop.run_until_complete(_run())
    loop.close()


with gr.Blocks() as demo:
    gr.Markdown("### libEnsemble Agent")

    with gr.Row():
        agent_dropdown = gr.Dropdown(
            label="Agent Script",
            choices=scan_agent_scripts(),
            value=scan_agent_scripts()[0] if scan_agent_scripts() else None,
            allow_custom_value=True,
            scale=2
        )
        scripts_dropdown = gr.Dropdown(
            label="Scripts Directory",
            choices=scan_script_dirs(),
            value=None,
            allow_custom_value=True,
            scale=2
        )
        run_btn = gr.Button("Run", variant="primary", scale=1)
        reset_btn = gr.Button("Reset", variant="stop", scale=1)

    scripts_dict = gr.State(value={})

    with gr.Row():
        output_logs = gr.Textbox(label="Logs", lines=20)
        with gr.Column():
            script_file_dropdown = gr.Dropdown(label="Generated Scripts", choices=[], value=None)
            output_script = gr.Code(label="Script Content", language="python", lines=10)
            output_plot = gr.Image(label="Plot", visible=False)

    def process_messages(scripts_state):
        import time
        scripts = scripts_state if scripts_state else {}
        script_names = list(scripts.keys())
        selected_script = script_names[0] if script_names else None
        logs = ""
        done = False
        task_started = False
        start_time = time.time()
        timeout = 300

        while not output_queue.empty():
            try:
                output_queue.get_nowait()
            except Empty:
                break

        wait_start = time.time()
        while not task_started and (time.time() - wait_start) < 10:
            try:
                msg_type, data = output_queue.get(timeout=0.1)
                if msg_type == "message":
                    msg = json.loads(data)
                    if msg["type"] == "log" and msg["text"].startswith("started:"):
                        task_started = True
                        logs += msg["text"] + "\n"
                        yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                        break
            except Empty:
                yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                time.sleep(0.1)

        if not task_started:
            yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
            return

        while not done and (time.time() - start_time) < timeout:
            try:
                msg_type, data = output_queue.get(timeout=0.1)

                if msg_type == "message":
                    msg = json.loads(data)

                    if msg["type"] == "log":
                        logs += msg["text"] + "\n"
                        yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                        if msg["text"].startswith("done:") or msg["text"].startswith("stopped"):
                            done = True
                            break

                    elif msg["type"] == "script":
                        scripts[msg["filename"]] = msg["content"]
                        script_names = list(scripts.keys())
                        selected_script = script_names[-1] if script_names else None
                        yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""

                elif msg_type == "error":
                    logs += f"Error: {data}\n"
                    yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                    done = True
                    break
            except Empty:
                yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                time.sleep(0.1)

    def send_and_clear(agent_script, scripts_dir):
        if agent_script and scripts_dir:
            # Just send the script name - backend will run from AGENT_DIR
            # Convert directory name to full path
            if not Path(scripts_dir).is_absolute():
                scripts_dir = str(AGENT_DIR / "tests" / scripts_dir)
            
            while not output_queue.empty():
                try:
                    output_queue.get_nowait()
                except Empty:
                    break
            msg = json.dumps({
                "agent_script": agent_script,  # Just the filename
                "scripts_dir": scripts_dir
            })
            message_queue.put(msg)
        return ""

    def reset_ui():
        while not output_queue.empty():
            try:
                output_queue.get_nowait()
            except Empty:
                break
        while not message_queue.empty():
            try:
                message_queue.get_nowait()
            except Empty:
                break
        return "", {}, gr.update(choices=[], value=None), ""

    def start_websocket():
        global ws_thread
        if ws_thread is None or not ws_thread.is_alive():
            stop_event.clear()
            ws_thread = threading.Thread(target=websocket_worker, daemon=True)
            ws_thread.start()

    def update_script_display(selected_name, scripts_state):
        if selected_name and selected_name in scripts_state:
            return scripts_state[selected_name]
        return ""

    demo.load(start_websocket)

    run_btn.click(
        send_and_clear,
        inputs=[agent_dropdown, scripts_dropdown],
        outputs=[output_logs]
    ).then(
        process_messages,
        inputs=[scripts_dict],
        outputs=[output_logs, scripts_dict, script_file_dropdown, output_script]
    )

    reset_btn.click(
        reset_ui,
        outputs=[output_logs, scripts_dict, script_file_dropdown, output_script]
    )

    script_file_dropdown.change(
        update_script_display,
        inputs=[script_file_dropdown, scripts_dict],
        outputs=output_script
    )


def start_uvicorn_server():
    """Start uvicorn server in background"""
    global uvicorn_process
    try:
        # Check if server is already running
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        if result == 0:
            print("✓ Uvicorn server already running on port 8000")
            return
    except:
        pass
    
    # Start uvicorn server
    print("Starting uvicorn server...")
    uvicorn_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--reload", "--port", "8000"],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to be ready (check if port is listening)
    max_wait = 3  # seconds
    waited = 0
    while waited < max_wait:
        if uvicorn_process.poll() is not None:
            # Process died
            print("✗ Failed to start uvicorn server")
            stderr = uvicorn_process.stderr.read().decode() if uvicorn_process.stderr else ""
            print(f"Error: {stderr}")
            return
        
        # Check if port is listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        if result == 0:
            print("✓ Uvicorn server started on port 8000")
            return
        
        time.sleep(0.5)
        waited += 0.5
    
    print("⚠ Uvicorn server may not be ready yet (timeout)")


if __name__ == "__main__":
    # Start uvicorn server before launching Gradio
    start_uvicorn_server()
    
    # Launch Gradio interface
    print("Starting Gradio interface...")
    demo.launch()
    
    # Cleanup: stop uvicorn when Gradio exits
    if uvicorn_process:
        print("\nStopping uvicorn server...")
        uvicorn_process.terminate()
        uvicorn_process.wait()
