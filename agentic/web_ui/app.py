import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from queue import Queue, Empty

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

AGENT_DIR = Path(__file__).parent.parent  # Go up from web_ui/ to agentic/
GENERATED_SCRIPTS_DIR = AGENT_DIR / "generated_scripts"


class Session:
    def __init__(self):
        self.output_queue = Queue()

    async def _send(self, ws, msg):
        await ws.send_text(json.dumps(msg))

    async def _log(self, ws, text):
        await self._send(ws, {"type": "log", "text": text})

    async def _send_scripts(self, ws):
        if not GENERATED_SCRIPTS_DIR.exists():
            return
        for f in sorted(GENERATED_SCRIPTS_DIR.glob("*.py")):
            await self._send(ws, {
                "type": "script",
                "filename": f.name,
                "content": f.read_text()
            })

    def _subprocess_thread(self, cmd, cwd):
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )
            for line in process.stdout:
                self.output_queue.put(("line", line.rstrip()))
            process.wait()
            self.output_queue.put(("exit", process.returncode))
        except Exception as e:
            self.output_queue.put(("error", str(e)))

    async def run_agent(self, agent_script, scripts_dir, ws, agent_dir=None):
        await self._log(ws, f"started: {agent_script} --scripts {scripts_dir}")

        # Use configured agent_dir or default
        run_dir = Path(agent_dir) if agent_dir else AGENT_DIR
        cmd = [sys.executable, agent_script, "--scripts", scripts_dir]

        # Clear queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except Empty:
                break

        thread = threading.Thread(
            target=self._subprocess_thread,
            args=(cmd, str(run_dir)),  # Run from configured directory
            daemon=True
        )
        thread.start()

        done = False
        while not done:
            try:
                msg_type, data = self.output_queue.get_nowait()
                if msg_type == "line":
                    await self._log(ws, data)
                    if "Saved:" in data:
                        await self._send_scripts(ws)
                elif msg_type == "exit":
                    await self._log(ws, f"\nProcess exited with code {data}")
                    await self._send_scripts(ws)
                    done = True
                elif msg_type == "error":
                    await self._log(ws, f"Error: {data}")
                    done = True
            except Empty:
                await asyncio.sleep(0.1)

        await self._log(ws, "done: complete")


sessions: dict[str, Session] = {}


@app.websocket("/ws/{session_id}")
async def ws_endpoint(ws: WebSocket, session_id: str):
    await ws.accept()
    s = sessions.setdefault(session_id, Session())
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            agent_script = msg.get("agent_script", "libe_agent_basic.py")
            scripts_dir = msg.get("scripts_dir", "")
            agent_dir = msg.get("agent_dir", None)
            if scripts_dir:
                await s.run_agent(agent_script, scripts_dir, ws, agent_dir=agent_dir)
    except WebSocketDisconnect:
        pass
