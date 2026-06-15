"""
Pomodoro Timer - Correct Display
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

HTML_CONTENT = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🍅 Pomodoro Timer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            background: #0a0a0a;
            color: #00ffcc;
            font-family: 'Segoe UI', 'Courier New', monospace;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        
        .container {
            text-align: center;
            padding: 20px;
            max-width: 750px;
            width: 100%;
        }
        
        h1 {
            font-size: 2.8em;
            margin-bottom: 15px;
            text-shadow: 0 0 20px rgba(0, 255, 204, 0.6);
            letter-spacing: 3px;
            font-weight: 300;
        }
        
        .info-panel {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin: 20px 0;
            font-size: 1.1em;
        }
        
        .info-item {
            background: #111;
            padding: 12px 25px;
            border-radius: 12px;
            border: 1px solid rgba(0, 255, 204, 0.2);
        }
        
        .info-item strong {
            font-size: 1.3em;
        }
        
        .clock {
            background: #0d0d0d;
            border: 2px solid rgba(0, 255, 204, 0.15);
            border-radius: 20px;
            padding: 25px;
            margin: 20px 0;
            box-shadow: 0 0 40px rgba(0, 255, 204, 0.08);
        }
        
        canvas {
            display: block;
            margin: 0 auto;
            max-width: 100%;
            height: auto;
        }
        
        .status {
            font-size: 1.6em;
            margin: 20px 0;
            min-height: 45px;
        }
        
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
            margin: 25px 0;
        }
        
        button {
            background: transparent;
            border: 2px solid #00ffcc;
            color: #00ffcc;
            padding: 14px 30px;
            font-size: 1.1em;
            cursor: pointer;
            border-radius: 12px;
            min-width: 130px;
            font-family: inherit;
        }
        
        button:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }
        
        .settings {
            margin-top: 25px;
            padding: 18px;
            background: #111;
            border: 1px solid rgba(0, 255, 204, 0.15);
            border-radius: 12px;
        }
        
        .setting-row {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .setting-row label {
            min-width: 200px;
            text-align: right;
        }
        
        .setting-row input {
            background: #1a1a1a;
            border: 1px solid #00ffcc;
            color: #00ffcc;
            padding: 10px;
            width: 75px;
            text-align: center;
            border-radius: 8px;
            font-size: 1.1em;
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #00ffcc;
            color: #0a0a0a;
            padding: 18px 30px;
            border-radius: 12px;
            z-index: 1000;
            font-weight: bold;
            animation: slideIn 0.5s ease;
        }
        
        @keyframes slideIn {
            from { transform: translateX(120%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .working { animation: pulse 2s infinite; }
        .break { color: #ffaa00 !important; animation: pulse 3s infinite; }
        .paused { color: #ff6666 !important; }
        
        .progress-bar {
            width: 100%;
            height: 4px;
            background: rgba(0, 255, 204, 0.1);
            border-radius: 2px;
            margin-top: 15px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00ffcc, #00ff88);
            transition: width 0.5s ease;
            width: 100%;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🍅 Pomodoro Timer</h1>
        
        <div class="info-panel">
            <div class="info-item">
                🍅 Сессий: <strong id="sessionCount">0</strong>
            </div>
            <div class="info-item">
                📍 Режим: <strong id="modeIndicator">Работа</strong>
            </div>
        </div>
        
        <div class="clock">
            <canvas id="clockCanvas" width="650" height="220"></canvas>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
        </div>
        
        <div class="status" id="status">Готов к работе</div>
        
        <div class="controls">
            <button id="startBtn" onclick="sendCommand('start')">▶ Старт</button>
            <button id="pauseBtn" onclick="sendCommand('pause')" disabled>⏸ Пауза</button>
            <button id="stopBtn" onclick="sendCommand('stop')" disabled>⏹ Стоп</button>
        </div>
        
        <div class="settings">
            <div class="setting-row">
                <label>⏱ Длительность работы (мин):</label>
                <input type="number" id="workDuration" value="25" min="1" max="60">
                <button onclick="updateSettings()">Применить</button>
            </div>
        </div>
    </div>
    
    <script>
        class AnimatedDisplay {
            constructor(canvasId) {
                this.canvas = document.getElementById(canvasId);
                this.ctx = this.canvas.getContext('2d');
                this.pointSize = 8;
                this.scale = 28;
                
                this.positions = {
                    minutes_tens: { x: 85, y: 55 },
                    minutes_ones: { x: 175, y: 55 },
                    seconds_tens: { x: 340, y: 55 },
                    seconds_ones: { x: 430, y: 55 }
                };
                
                this.currentPoints = {};
                this.animations = [];
                
                this.clearCanvas();
                this.drawColon();
                this.animate();
            }
            
            drawPoint(x, y, alpha = 1, size = null) {
                const ctx = this.ctx;
                const pointSize = size || this.pointSize;
                
                ctx.shadowBlur = 15 * alpha;
                ctx.shadowColor = `rgba(0, 255, 204, ${0.6 * alpha})`;
                
                const gradient = ctx.createRadialGradient(x, y, 0, x, y, pointSize);
                gradient.addColorStop(0, `rgba(255, 255, 255, ${alpha})`);
                gradient.addColorStop(0.3, `rgba(200, 255, 230, ${alpha * 0.9})`);
                gradient.addColorStop(0.6, `rgba(0, 255, 204, ${alpha * 0.7})`);
                gradient.addColorStop(1, `rgba(0, 255, 204, 0)`);
                
                ctx.fillStyle = gradient;
                ctx.beginPath();
                ctx.arc(x, y, pointSize * 1.5, 0, Math.PI * 2);
                ctx.fill();
                
                ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.8})`;
                ctx.beginPath();
                ctx.arc(x, y, pointSize * 0.3, 0, Math.PI * 2);
                ctx.fill();
                
                ctx.shadowBlur = 0;
            }
            
            drawColon() {
                const ctx = this.ctx;
                ctx.shadowBlur = 15;
                ctx.shadowColor = 'rgba(0, 255, 204, 0.6)';
                
                [75, 120].forEach(y => {
                    const gradient = ctx.createRadialGradient(300, y, 0, 300, y, 8);
                    gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
                    gradient.addColorStop(0.5, 'rgba(0, 255, 204, 1)');
                    gradient.addColorStop(1, 'rgba(0, 255, 204, 0)');
                    
                    ctx.fillStyle = gradient;
                    ctx.beginPath();
                    ctx.arc(300, y, 8, 0, Math.PI * 2);
                    ctx.fill();
                });
                
                ctx.shadowBlur = 0;
            }
            
            clearCanvas() {
                this.ctx.fillStyle = '#0d0d0d';
                this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            }
            
            // Конвертация: backend шлет y от 0 (верх) до 5.5 (низ)
            // Canvas: y увеличивается вниз
            // Нужно перевернуть: 5.5 - y
            convertToCanvas(point, pos) {
                return {
                    x: pos.x + point[0] * this.scale,
                    y: pos.y + (5.5 - point[1]) * this.scale  // ВОТ ТУТ ИНВЕРСИЯ
                };
            }
            
            animateTransition(position, fromPoints, toPoints) {
                const pos = this.positions[position];
                if (!pos) return;
                
                const toCoords = toPoints.map(p => this.convertToCanvas(p, pos));
                
                let fromCoords;
                if (!fromPoints || fromPoints.length === 0) {
                    const cx = pos.x + 2.5 * this.scale / 2;
                    const cy = pos.y + 5.5 * this.scale / 2;
                    fromCoords = toCoords.map(() => ({
                        x: cx + (Math.random() - 0.5) * 20,
                        y: cy + (Math.random() - 0.5) * 20
                    }));
                } else {
                    fromCoords = fromPoints.map(p => this.convertToCanvas(p, pos));
                }
                
                this.animations = this.animations.filter(a => a.position !== position);
                this.animations.push({
                    position,
                    fromCoords,
                    toCoords,
                    startTime: performance.now(),
                    duration: 300 + Math.random() * 200
                });
            }
            
            updateDisplay(displayData, animate = true) {
                for (const [position, data] of Object.entries(displayData)) {
                    const newPoints = data.points || [];
                    
                    if (animate && this.currentPoints[position]) {
                        this.animateTransition(position, this.currentPoints[position], newPoints);
                    }
                    
                    this.currentPoints[position] = newPoints;
                }
            }
            
            animate() {
                this.clearCanvas();
                this.drawColon();
                
                const now = performance.now();
                const activePositions = new Set(this.animations.map(a => a.position));
                
                // Статичные позиции
                for (const [position, points] of Object.entries(this.currentPoints)) {
                    if (activePositions.has(position)) continue;
                    
                    const pos = this.positions[position];
                    if (!pos) continue;
                    
                    points.forEach(point => {
                        const c = this.convertToCanvas(point, pos);
                        this.drawPoint(c.x, c.y);
                    });
                }
                
                // Анимируемые позиции
                this.animations = this.animations.filter(anim => {
                    const elapsed = now - anim.startTime;
                    const progress = Math.min(1, elapsed / anim.duration);
                    const t = progress < 0.5 ? 4*progress**3 : 1 - (-2*progress + 2)**3 / 2;
                    
                    const maxPoints = Math.max(anim.fromCoords.length, anim.toCoords.length);
                    
                    for (let i = 0; i < maxPoints; i++) {
                        const fi = Math.min(i, anim.fromCoords.length - 1);
                        const ti = Math.min(i, anim.toCoords.length - 1);
                        
                        const from = anim.fromCoords[fi];
                        const to = anim.toCoords[ti];
                        
                        let x, y, alpha, size = this.pointSize;
                        
                        if (i >= anim.fromCoords.length) {
                            const ap = Math.max(0, (progress - 0.3) / 0.7);
                            const st = 1 - (1-ap)**3 * Math.cos(ap * Math.PI * 3);
                            x = to.x; y = to.y;
                            alpha = st;
                            size *= (0.5 + st * 0.5);
                        } else if (i >= anim.toCoords.length) {
                            const dp = Math.min(1, progress / 0.3);
                            x = from.x + (to.x - from.x) * dp;
                            y = from.y + (to.y - from.y) * dp;
                            alpha = 1 - dp;
                        } else {
                            x = from.x + (to.x - from.x) * t;
                            y = from.y + (to.y - from.y) * t;
                            alpha = 1;
                        }
                        
                        if (alpha > 0.01) this.drawPoint(x, y, alpha, size);
                    }
                    
                    return progress < 1;
                });
                
                requestAnimationFrame(() => this.animate());
            }
        }
        
        const display = new AnimatedDisplay('clockCanvas');
        let ws = null;
        let reconnectAttempts = 0;
        let previousDigits = {};
        
        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = () => {
                reconnectAttempts = 0;
                document.getElementById('status').textContent = 'Готов к работе';
                document.getElementById('status').className = 'status';
                updateButtons('stopped');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'timer_update') {
                    let hasChanges = false;
                    if (data.display) {
                        for (const [pos, info] of Object.entries(data.display)) {
                            if (previousDigits[pos] !== info.digit) {
                                hasChanges = true;
                                break;
                            }
                        }
                        display.updateDisplay(data.display, hasChanges);
                        for (const [pos, info] of Object.entries(data.display)) {
                            previousDigits[pos] = info.digit;
                        }
                    }
                    
                    const statusEl = document.getElementById('status');
                    const modeEl = document.getElementById('modeIndicator');
                    const progressFill = document.getElementById('progressFill');
                    
                    const totalDuration = data.state === 'working' ? 1500 : 
                                        data.sessions % 4 === 0 ? 900 : 300;
                    const remaining = data.minutes * 60 + data.seconds;
                    progressFill.style.width = `${Math.min(100, Math.max(0, ((totalDuration - remaining) / totalDuration) * 100))}%`;
                    
                    switch(data.state) {
                        case 'working':
                            statusEl.textContent = '⚡ Работаем!';
                            statusEl.className = 'status working';
                            modeEl.textContent = 'Работа';
                            break;
                        case 'break':
                            statusEl.textContent = '☕ Перерыв';
                            statusEl.className = 'status break';
                            modeEl.textContent = 'Отдых';
                            break;
                        case 'paused':
                            statusEl.textContent = '⏸ Пауза';
                            statusEl.className = 'status paused';
                            break;
                        default:
                            statusEl.textContent = 'Готов к работе';
                            statusEl.className = 'status';
                            modeEl.textContent = 'Работа';
                            progressFill.style.width = '100%';
                    }
                    
                    document.getElementById('sessionCount').textContent = data.sessions || 0;
                    updateButtons(data.state);
                    
                    if (data.phase_changed) {
                        showNotification(data.state === 'working' ? '🔔 Время работать!' : '🔔 Время отдыхать!');
                    }
                }
            };
            
            ws.onclose = () => {
                document.getElementById('status').textContent = 'Переподключение...';
                document.getElementById('status').className = 'status paused';
                setTimeout(connectWebSocket, Math.min(1000 * 2**reconnectAttempts++, 10000));
            };
        }
        
        function updateButtons(state) {
            const startBtn = document.getElementById('startBtn');
            const pauseBtn = document.getElementById('pauseBtn');
            const stopBtn = document.getElementById('stopBtn');
            
            startBtn.disabled = state !== 'stopped' && state !== 'paused';
            pauseBtn.disabled = state === 'stopped' || state === 'paused';
            stopBtn.disabled = state === 'stopped';
        }
        
        function sendCommand(action) {
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action }));
        }
        
        function updateSettings() {
            const d = parseInt(document.getElementById('workDuration').value);
            if (d >= 1 && d <= 60 && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ action: 'set_duration', duration: d }));
            }
        }
        
        function showNotification(message) {
            const n = document.createElement('div');
            n.className = 'notification';
            n.textContent = message;
            document.body.appendChild(n);
            setTimeout(() => n.remove(), 2500);
        }
        
        document.addEventListener('keydown', (e) => {
            if (e.key === ' ') {
                e.preventDefault();
                const sb = document.getElementById('startBtn');
                sb.disabled ? sendCommand('pause') : sendCommand('start');
            } else if (e.key === 'Escape') sendCommand('stop');
        });
        
        connectWebSocket();
    </script>
</body>
</html>"""

with open(os.path.join(STATIC_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(HTML_CONTENT)

# Backend
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
                    # ИНВЕРСИЯ ЗДЕСЬ: 10-y чтобы верх матрицы был верхом на экране
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

renderer = DigitRenderer()
timer = PomodoroTimer()

@app.get("/")
async def root():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
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

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🍅 Pomodoro Timer Starting...")
    print("=" * 50)
    print("Open your browser at: http://localhost:8000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")