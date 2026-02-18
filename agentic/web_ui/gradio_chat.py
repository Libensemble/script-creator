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
DEFAULT_AGENT_DIR = Path(__file__).parent.parent
DEFAULT_TESTS_DIR = DEFAULT_AGENT_DIR / "tests"
DEFAULT_AGENT_PATTERN = "libe_agent*.py"

ws_conn = None
message_queue = Queue()
output_queue = Queue()
ws_thread = None
stop_event = threading.Event()
uvicorn_process = None


def scan_agent_scripts(agent_dir_path, pattern=None):
    if pattern is None:
        pattern = DEFAULT_AGENT_PATTERN
    try:
        if not agent_dir_path:
            return []
        agent_dir = Path(agent_dir_path)
        if not agent_dir.exists():
            print(f"Warning: Agent directory does not exist: {agent_dir_path}")
            return []
        if not agent_dir.is_dir():
            print(f"Warning: Agent path is not a directory: {agent_dir_path}")
            return []
        exclude = {"app.py", "gradio_chat.py", "__init__.py"}
        scripts = [f.name for f in sorted(agent_dir.glob(pattern)) if f.name not in exclude]
        return scripts
    except Exception as e:
        print(f"Error scanning agent scripts: {e}")
        return []


def scan_script_dirs(scripts_dir_path):
    try:
        if not scripts_dir_path:
            return []
        scripts_dir = Path(scripts_dir_path)
        if not scripts_dir.exists():
            print(f"Warning: Scripts directory does not exist: {scripts_dir_path}")
            return []
        if not scripts_dir.is_dir():
            print(f"Warning: Scripts path is not a directory: {scripts_dir_path}")
            return []
        dirs = [d.name for d in sorted(scripts_dir.iterdir()) if d.is_dir() and not d.name.startswith("_")]
        return dirs
    except Exception as e:
        print(f"Error scanning script directories: {e}")
        return []


def scan_versions(agent_dir_path):
    """Scan for version directories in generated_scripts/versions/"""
    try:
        if not agent_dir_path:
            return ["latest"]
        agent_dir = Path(agent_dir_path)
        versions_dir = agent_dir / "generated_scripts" / "versions"
        if not versions_dir.exists():
            return ["latest"]
        versions = ["latest"] + [d.name for d in sorted(versions_dir.iterdir(), reverse=True) if d.is_dir() and not d.name.startswith("_")]
        return versions
    except Exception as e:
        print(f"Error scanning versions: {e}")
        import traceback
        traceback.print_exc()
        return ["latest"]




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


_init_agents = scan_agent_scripts(str(DEFAULT_AGENT_DIR))
_init_tests = scan_script_dirs(str(DEFAULT_TESTS_DIR))
_init_versions = scan_versions(str(DEFAULT_AGENT_DIR))

with gr.Blocks() as demo:
    with gr.Row():
        gr.Markdown("### libEnsemble Agent")
        with gr.Column(scale=0, min_width=60):
            settings_btn = gr.Button("⚙️", size="sm")

    agent_dir_state = gr.State(value=str(DEFAULT_AGENT_DIR))
    scripts_dir_state = gr.State(value=str(DEFAULT_TESTS_DIR))
    agent_pattern_state = gr.State(value=DEFAULT_AGENT_PATTERN)
    settings_visible = gr.State(value=False)

    with gr.Column(visible=False) as settings_modal:
        with gr.Column(elem_classes="modal-content"):
            gr.Markdown("### Settings")
            agent_dir_input = gr.Textbox(label="Agent Directory", value=str(DEFAULT_AGENT_DIR))
            scripts_dir_input = gr.Textbox(label="Scripts Parent Directory", value=str(DEFAULT_TESTS_DIR))
            agent_pattern_input = gr.Textbox(label="Agent Script Pattern", value=DEFAULT_AGENT_PATTERN)
            with gr.Row():
                apply_settings_btn = gr.Button("Apply", variant="primary", size="sm")
                close_settings_btn = gr.Button("Close", size="sm")

    with gr.Row():
        agent_dropdown = gr.Dropdown(
            label="Agent Script", choices=_init_agents,
            value=_init_agents[0] if _init_agents else None,
            allow_custom_value=True, scale=2
        )
        scripts_dropdown = gr.Dropdown(
            label="Scripts Directory", choices=_init_tests,
            value=None, allow_custom_value=True, scale=2
        )
        run_btn = gr.Button("Run", variant="primary")
        reset_btn = gr.Button("Reset", variant="stop")

    scripts_dict = gr.State(value={})

    with gr.Row():
        output_logs = gr.Textbox(label="Logs", lines=20)
        with gr.Column():
            version_dropdown = gr.Dropdown(
                label="libE scripts",
                choices=_init_versions,
                value="latest"
            )
            script_file_dropdown = gr.Dropdown(label="Generated Scripts", choices=[], value=None)
            output_script = gr.Code(label="Script Content", language="python", lines=10)
            output_plot = gr.Image(label="Plot", visible=False)

    def process_messages(scripts_state):
        import time
        try:
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
        except Exception as e:
            error_msg = f"ERROR in process_messages: {str(e)}"
            print(error_msg)
            return error_msg, {}, gr.update(choices=[], value=None), ""

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
                elif msg_type == "error":
                    logs += f"ERROR: {data}\n"
                    yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                    return
            except Empty:
                yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                time.sleep(0.1)
            except Exception as e:
                error_msg = f"ERROR waiting for task: {str(e)}"
                logs += error_msg + "\n"
                yield logs, scripts, gr.update(choices=script_names, value=selected_script), scripts.get(selected_script, "") if selected_script else ""
                return

        if not task_started:
            logs += "ERROR: Task did not start within 10 seconds. Check websocket connection.\n"
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

    def toggle_settings(current_visible):
        return not current_visible, gr.update(visible=not current_visible)
    
    def apply_settings(agent_dir, agent_pattern, scripts_dir):
        new_agent_dir = agent_dir.strip() if agent_dir and agent_dir.strip() else str(DEFAULT_AGENT_DIR)
        new_agent_pattern = agent_pattern.strip() if agent_pattern and agent_pattern.strip() else DEFAULT_AGENT_PATTERN
        new_scripts_dir = scripts_dir.strip() if scripts_dir and scripts_dir.strip() else str(DEFAULT_TESTS_DIR)
        
        agent_choices = scan_agent_scripts(new_agent_dir, new_agent_pattern)
        scripts_choices = scan_script_dirs(new_scripts_dir)
        version_choices = scan_versions(new_agent_dir)
        
        return (
            new_agent_dir,
            new_agent_pattern,
            new_scripts_dir,
            gr.update(choices=agent_choices, value=agent_choices[0] if agent_choices else None),
            gr.update(choices=scripts_choices, value=None),
            gr.update(choices=version_choices, value="latest"),
            False,  # settings_visible - close modal
            gr.update(visible=False)  # settings_modal
        )
    
    def send_and_clear(agent_script, scripts_dir, agent_dir_state_val, scripts_dir_state_val):
        try:
            if not agent_script:
                return "ERROR: No agent script selected"
            if not scripts_dir:
                return "ERROR: No scripts directory selected"
            
            agent_dir = Path(agent_dir_state_val) if agent_dir_state_val else DEFAULT_AGENT_DIR
            scripts_base_dir = Path(scripts_dir_state_val) if scripts_dir_state_val else DEFAULT_TESTS_DIR
            
            if not Path(scripts_dir).is_absolute():
                scripts_dir = str(scripts_base_dir / scripts_dir)
            
            while not output_queue.empty():
                try:
                    output_queue.get_nowait()
                except Empty:
                    break
            
            if not ws_thread or not ws_thread.is_alive():
                return "ERROR: Websocket not connected. Try refreshing the page."
            
            msg = json.dumps({
                "agent_script": agent_script,
                "scripts_dir": scripts_dir,
                "agent_dir": str(agent_dir)
            })
            message_queue.put(msg)
            return ""
        except Exception as e:
            return f"ERROR in send_and_clear: {str(e)}"
    
    def load_version_scripts(version, agent_dir_state_val):
        """Load scripts directly from a version directory"""
        agent_dir = Path(agent_dir_state_val) if agent_dir_state_val else DEFAULT_AGENT_DIR
        if version and version != "latest":
            scripts_dir = agent_dir / "generated_scripts" / "versions" / version
        else:
            scripts_dir = agent_dir / "generated_scripts"

        scripts = {}
        if scripts_dir.exists():
            for f in sorted(scripts_dir.glob("*.py")):
                scripts[f.name] = f.read_text()

        names = list(scripts.keys())
        selected = names[0] if names else None
        content = scripts.get(selected, "") if selected else ""
        return scripts, gr.update(choices=names, value=selected), content

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

    settings_btn.click(
        toggle_settings,
        inputs=[settings_visible],
        outputs=[settings_visible, settings_modal]
    )
    
    def close_settings():
        return False, gr.update(visible=False)
    
    close_settings_btn.click(
        close_settings,
        outputs=[settings_visible, settings_modal]
    )
    
    apply_settings_btn.click(
        apply_settings,
        inputs=[agent_dir_input, agent_pattern_input, scripts_dir_input],
        outputs=[agent_dir_state, agent_pattern_state, scripts_dir_state, agent_dropdown, scripts_dropdown, version_dropdown, settings_visible, settings_modal]
    )

    def refresh_versions(agent_dir_state_val):
        """Refresh version list"""
        versions = scan_versions(agent_dir_state_val)
        return gr.update(choices=versions)
    
    def refresh_agents(agent_dir_state_val, agent_pattern_state_val):
        """Refresh agent list"""
        agents = scan_agent_scripts(agent_dir_state_val, agent_pattern_state_val)
        return gr.update(choices=agents, value=agents[0] if agents else None)
    
    def run_with_error_check(agent_script, scripts_dir, agent_dir_state_val, scripts_dir_state_val):
        error_msg = send_and_clear(agent_script, scripts_dir, agent_dir_state_val, scripts_dir_state_val)
        if error_msg:
            return error_msg
        return ""
    
    run_btn.click(
        run_with_error_check,
        inputs=[agent_dropdown, scripts_dropdown, agent_dir_state, scripts_dir_state],
        outputs=[output_logs]
    ).then(
        process_messages,
        inputs=[scripts_dict],
        outputs=[output_logs, scripts_dict, script_file_dropdown, output_script]
    ).then(
        refresh_versions,
        inputs=[agent_dir_state],
        outputs=[version_dropdown]
    ).then(
        refresh_agents,
        inputs=[agent_dir_state, agent_pattern_state],
        outputs=[agent_dropdown]
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
    
    version_dropdown.change(
        load_version_scripts,
        inputs=[version_dropdown, agent_dir_state],
        outputs=[scripts_dict, script_file_dropdown, output_script]
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
