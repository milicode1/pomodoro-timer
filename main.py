"""
Pomodoro Timer - OPTIMIZED VERSION
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json
import time
import os

app = FastAPI(title="Pomodoro Timer")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)


class PomodoroTimer:
    def __init__(self):
        self.work_dur = 1500
        self.break_dur = 300
        self.long_break = 900
        self.state = "stopped"
        self.remaining = self.work_dur
        self.start_t = None
        self.sessions = 0
        self.is_work = True
        self.paused_state = None
    
    def start(self):
        if self.state == "stopped":
            self.state = "working"
            self.remaining = self.work_dur
            self.is_work = True
        elif self.state == "paused":
            if self.paused_state:
                self.state = self.paused_state
            else:
                self.state = "working"
            self.paused_state = None
        self.start_t = time.time()
    
    def pause(self):
        if self.state in ["working", "break"]:
            self.remaining = max(0, self.remaining - (time.time() - self.start_t))
            self.paused_state = self.state
            self.state = "paused"
    
    def stop(self):
        self.state = "stopped"
        self.remaining = self.work_dur
        self.start_t = None
        self.is_work = True
        self.paused_state = None
    
    def get_remaining(self):
        if self.state == "stopped":
            return self.work_dur
        if self.state == "paused":
            return self.remaining
        return max(0, self.remaining - (time.time() - self.start_t))
    
    def get_total_duration(self):
        """Возвращает общую длительность текущего режима"""
        if self.state == "working":
            return self.work_dur
        elif self.state == "break":
            return self.long_break if self.sessions % 4 == 0 else self.break_dur
        elif self.paused_state == "break":
            return self.long_break if self.sessions % 4 == 0 else self.break_dur
        return self.work_dur
    
    def update(self):
        if self.state in ["working", "break"]:
            if self.get_remaining() <= 0:
                if self.is_work:
                    self.sessions += 1
                    self.state = "break"
                    self.is_work = False
                    self.remaining = self.long_break if self.sessions % 4 == 0 else self.break_dur
                else:
                    self.state = "working"
                    self.is_work = True
                    self.remaining = self.work_dur
                self.start_t = time.time()
                return True
        return False
    
    def get_time(self):
        t = int(self.get_remaining())
        return t // 60, t % 60


timer = PomodoroTimer()


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    m, s = timer.get_time()
    total_dur = timer.get_total_duration()
    
    await websocket.send_json({
        "type": "timer_update",
        "minutes": m,
        "seconds": s,
        "state": timer.state,
        "sessions": timer.sessions,
        "phase_changed": False,
        "total_duration": total_dur
    })
    
    last_minutes = m
    last_seconds = s
    last_state = timer.state
    last_total_duration = total_dur
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "start":
                    timer.start()
                elif action == "pause":
                    timer.pause()
                elif action == "stop":
                    timer.stop()
                elif action == "set_duration":
                    timer.work_dur = cmd.get("duration", 25) * 60
                    if timer.state == "stopped":
                        timer.remaining = timer.work_dur
            except asyncio.TimeoutError:
                pass
            
            changed = timer.update()
            m, s = timer.get_time()
            total_dur = timer.get_total_duration()
            
            if (m != last_minutes or s != last_seconds or 
                timer.state != last_state or changed or
                total_dur != last_total_duration):
                
                await websocket.send_json({
                    "type": "timer_update",
                    "minutes": m,
                    "seconds": s,
                    "state": timer.state,
                    "sessions": timer.sessions,
                    "phase_changed": changed,
                    "total_duration": total_dur
                })
                
                last_minutes = m
                last_seconds = s
                last_state = timer.state
                last_total_duration = total_dur
            
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")