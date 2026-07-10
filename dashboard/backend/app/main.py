from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from typing import Any

app = FastAPI(title="AgentPulse Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE_FILE = "/tmp/agentpulse/state.json"

@app.get("/health")
async def health():
    return {"ok": True, "service": "agentpulse-dashboard"}

@app.get("/api/state")
async def get_real_state():
    """Serve real state from the running agentpulse agent"""
    if not os.path.exists(STATE_FILE):
        return {
            "last_run": None,
            "pending": [],
            "history": [],
            "blocked_ips": [],
            "agents": {}
        }
    
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        
        # Normalize to what the frontend expects
        return {
            "last_run": data.get("last_run"),
            "pending": data.get("pending", []),
            "history": data.get("history", []),
            "blocked_ips": data.get("blocked_ips", []),
            "agents": data.get("agents", {})
        }
    except Exception as e:
        return {"error": str(e)}