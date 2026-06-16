"""
Pomodoro Timer - OPTIMIZED VERSION
Сохранена оригинальная логика анимации, оптимизирован сетевой трафик
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

# ============================================
# Backend Classes
# ============================================

class DigitRenderer:
    def __init__(self):
        self.digits = self._create_digits()
    
    def _create_digits(self):
        digits = {i: [[0]*5 for _ in range(11)] for i in range(10)}
        
        # 0
        for y in range(1, 10): digits[0][y][0] = digits[0][y][4] = 1
        for x in range(1, 4): digits[0][0][x] = digits[0][10][x] = 1
        digits[0][4][3] = digits[0][5][2] = digits[0][6][1] = 1
        
        # 1
        for y in range(11): digits[1][y][2] = 1
        digits[1][1][1] = digits[1][2][0] = 1
        for x in range(5): digits[1][10][x] = 1
        
        # 2
        for x in range(1, 4): digits[2][0][x] = 1
        digits[2][1][0] = digits[2][2][0] = 1
        for y in range(1, 6): digits[2][y][4] = 1
        digits[2][6][3] = digits[2][7][2] = digits[2][8][1] = digits[2][9][0] = 1
        for x in range(5): digits[2][10][x] = 1
        
        # 3
        for y in [1,2,8,9]: digits[3][y][0] = 1
        for y in list(range(1,5)) + list(range(6,10)): digits[3][y][4] = 1
        for x in range(1, 4): digits[3][0][x] = digits[3][5][x] = digits[3][10][x] = 1
        
        # 4
        for y in range(6): digits[4][y][0] = 1
        for y in range(1, 11): digits[4][y][3] = 1
        for x in range(5): digits[4][5][x] = 1
        
        # 5
        for x in range(5): digits[5][0][x] = 1
        for x in range(1, 4): digits[5][4][x] = digits[5][10][x] = 1
        for y in range(1, 6): digits[5][y][0] = 1
        for y in range(5, 10): digits[5][y][4] = 1
        digits[5][9][0] = 1
        
        # 6
        for x in range(1, 4): digits[6][0][x] = digits[6][4][x] = digits[6][10][x] = 1
        for y in range(1, 10): digits[6][y][0] = 1
        for y in range(5, 10): digits[6][y][4] = 1
        digits[6][1][4] = 1
        
        # 7
        for x in range(5): digits[7][0][x] = 1
        digits[7][1][0] = digits[7][2][0] = 1
        for y in range(1, 4): digits[7][y][4] = 1
        digits[7][4][3] = digits[7][5][2] = 1
        for y in range(6, 11): digits[7][y][2] = 1
        
        # 8
        for y in list(range(1,5)) + list(range(6,10)):
            digits[8][y][0] = digits[8][y][4] = 1
        for x in range(1, 4): digits[8][0][x] = digits[8][5][x] = digits[8][10][x] = 1
        
        # 9
        for y in range(1, 5): digits[9][y][0] = 1
        for y in range(1, 10): digits[9][y][4] = 1
        for x in range(1, 4): digits[9][0][x] = digits[9][5][x] = digits[9][10][x] = 1
        digits[9][9][0] = 1
        
        return digits
    
    def get_coords(self, digit):
        coords = []
        for y in range(11):
            for x in range(5):
                if self.digits.get(digit, [[0]*5]*11)[y][x]:
                    coords.append([x * 0.5, (10 - y) * 0.5])
        return coords
    
    def get_display(self, m, s):
        t = f"{m:02d}{s:02d}"
        return {f"{p}_{o}": {"digit": int(t[i]), "points": self.get_coords(int(t[i]))}
                for i, (p, o) in enumerate([("minutes","tens"),("minutes","ones"),
                                            ("seconds","tens"),("seconds","ones")])}


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
    
    def start(self):
        if self.state == "stopped":
            self.state = "working"
            self.remaining = self.work_dur
            self.is_work = True
        elif self.state == "paused":
            self.state = "working"
        self.start_t = time.time()
    
    def pause(self):
        if self.state in ["working", "break"]:
            self.remaining = max(0, self.remaining - (time.time() - self.start_t))
            self.state = "paused"
    
    def stop(self):
        self.state = "stopped"
        self.remaining = self.work_dur
        self.start_t = None
        self.is_work = True
    
    def get_remaining(self):
        if self.state == "stopped": return self.work_dur
        if self.state == "paused": return self.remaining
        return max(0, self.remaining - (time.time() - self.start_t))
    
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


# ============================================
# Инициализация
# ============================================

renderer = DigitRenderer()
timer = PomodoroTimer()


# ============================================
# Роуты
# ============================================

@app.get("/")
async def root():
    """Отдаёт index.html из папки static"""
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                cmd = json.loads(data)
                action = cmd.get("action")
                
                if action == "start": timer.start()
                elif action == "pause": timer.pause()
                elif action == "stop": timer.stop()
                elif action == "set_duration":
                    timer.work_dur = cmd.get("duration", 25) * 60
                    if timer.state == "stopped":
                        timer.remaining = timer.work_dur
            except asyncio.TimeoutError:
                pass
            
            changed = timer.update()
            m, s = timer.get_time()
            
            await websocket.send_json({
                "type": "timer_update",
                "minutes": m, "seconds": s,
                "display": renderer.get_display(m, s),
                "state": timer.state,
                "sessions": timer.sessions,
                "phase_changed": changed
            })
            
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass


# Монтируем статику (на случай других ресурсов)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============================================
# Запуск
# ============================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🍅 Pomodoro Timer - OPTIMIZED")
    print("🎬 nearest ↔ LURD (original logic preserved)")
    print("⚡ Gradient caching enabled")
    print("=" * 50)
    print("Open: http://localhost:8000")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")