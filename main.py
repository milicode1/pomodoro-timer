"""
Pomodoro Timer - MULTIUSER (до 20 человек)
✅ Каждому пользователю — свой персональный таймер
✅ Без комнат — у каждого свой независимый таймер
✅ Событийная модель
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json
import time
import os

app = FastAPI(title="Pomodoro Timer - MultiUser")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

MAX_CLIENTS = 20
active_clients = set()


class PersonalTimer:
    """Персональный таймер для одного пользователя"""
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
        self._event = asyncio.Event()
    
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
        self._notify()
    
    def pause(self):
        if self.state in ["working", "break"]:
            self.remaining = max(0, self.remaining - (time.time() - self.start_t))
            self.paused_state = self.state
            self.state = "paused"
            self._notify()
    
    def stop(self):
        self.state = "stopped"
        self.remaining = self.work_dur
        self.start_t = None
        self.is_work = True
        self.paused_state = None
        self._notify()
    
    def set_duration(self, minutes: int):
        self.work_dur = minutes * 60
        if self.state == "stopped":
            self.remaining = self.work_dur
            self._notify()
    
    def get_remaining(self):
        if self.state == "stopped":
            return self.work_dur
        if self.state == "paused":
            return self.remaining
        return max(0, self.remaining - (time.time() - self.start_t))
    
    def get_total_duration(self):
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
                self._notify()
                return True
        return False
    
    def get_time(self):
        t = int(self.get_remaining())
        return t // 60, t % 60
    
    def _notify(self):
        self._event.set()
        self._event.clear()
    
    def get_sleep_time(self):
        if self.state in ["working", "break"]:
            remaining = self.get_remaining()
            next_tick = remaining - int(remaining)
            if next_tick <= 0:
                next_tick = 1.0
            return next_tick
        return None


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/stats")
async def stats():
    return {"active_users": len(active_clients), "max_users": MAX_CLIENTS}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    # Проверяем лимит
    if len(active_clients) >= MAX_CLIENTS:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": f"Сервер заполнен (максимум {MAX_CLIENTS} человек)"
        })
        await websocket.close()
        return
    
    await websocket.accept()
    active_clients.add(websocket)
    
    # Персональный таймер для этого пользователя
    timer = PersonalTimer()
    
    # Отправляем начальное состояние
    m, s = timer.get_time()
    total_dur = timer.get_total_duration()
    
    await websocket.send_json({
        "type": "timer_update",
        "minutes": m,
        "seconds": s,
        "state": timer.state,
        "sessions": timer.sessions,
        "phase_changed": False,
        "total_duration": total_dur,
        "online": len(active_clients)
    })
    
    last_minutes = m
    last_seconds = s
    last_state = timer.state
    last_total_duration = total_dur
    
    # Фоновая задача для таймера
    async def timer_task():
        nonlocal last_minutes, last_seconds, last_state, last_total_duration
        
        try:
            while True:
                sleep_time = timer.get_sleep_time()
                if sleep_time is not None:
                    try:
                        await asyncio.wait_for(timer._event.wait(), timeout=sleep_time)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await timer._event.wait()
                
                changed = timer.update()
                m, s = timer.get_time()
                total_dur = timer.get_total_duration()
                
                if (m != last_minutes or s != last_seconds or 
                    timer.state != last_state or changed or
                    total_dur != last_total_duration):
                    
                    try:
                        await websocket.send_json({
                            "type": "timer_update",
                            "minutes": m,
                            "seconds": s,
                            "state": timer.state,
                            "sessions": timer.sessions,
                            "phase_changed": changed,
                            "total_duration": total_dur,
                            "online": len(active_clients)
                        })
                        
                        last_minutes = m
                        last_seconds = s
                        last_state = timer.state
                        last_total_duration = total_dur
                    except:
                        break
        except asyncio.CancelledError:
            pass
    
    task = asyncio.create_task(timer_task())
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "start":
                    timer.start()
                elif action == "pause":
                    timer.pause()
                elif action == "stop":
                    timer.stop()
                elif action == "set_duration":
                    timer.set_duration(cmd.get("duration", 25))
                    
            except WebSocketDisconnect:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        active_clients.discard(websocket)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🍅 Pomodoro Timer - MULTIUSER")
    print(f"👥 До {MAX_CLIENTS} персональных таймеров")
    print("🔗 ws://host:8000/ws")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")