"""
Pomodoro Timer - MULTIUSER (до 20 человек) + PWA с офлайн-режимом
✅ Каждому пользователю — свой персональный таймер
✅ Без комнат — у каждого свой независимый таймер
✅ Событийная модель
✅ PWA с офлайн-работой — таймер тикает без интернета
✅ Синхронизация при восстановлении связи
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
import time
import os
from datetime import datetime
from typing import Optional, Dict

app = FastAPI(title="Pomodoro Timer - MultiUser PWA Offline")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

MAX_CLIENTS = 20
active_clients: Dict[str, dict] = {}


class PersonalTimer:
    """Персональный таймер для одного пользователя"""
    def __init__(self, client_id: str = None):
        self.work_dur = 1500  # 25 минут
        self.break_dur = 300  # 5 минут
        self.long_break = 900  # 15 минут
        self.state = "stopped"
        self.remaining = self.work_dur
        self.start_t = None
        self.sessions = 0
        self.is_work = True
        self.paused_state = None
        self._event = asyncio.Event()
        self.client_id = client_id
        self.last_sync_time = time.time()
        self.offline_start_time = None  # Время начала офлайн-сессии
    
    def start(self, from_sync: bool = False, sync_time: float = None):
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
        
        if from_sync and sync_time:
            self.start_t = sync_time
        else:
            self.start_t = time.time()
        
        self.last_sync_time = time.time()
        self._notify()
    
    def pause(self, from_sync: bool = False, sync_remaining: float = None):
        if self.state in ["working", "break"]:
            if from_sync and sync_remaining is not None:
                self.remaining = sync_remaining
            else:
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
    
    def get_state_snapshot(self) -> dict:
        """Получить полное состояние таймера для синхронизации"""
        m, s = self.get_time()
        return {
            "state": self.state,
            "remaining": self.get_remaining(),
            "minutes": m,
            "seconds": s,
            "sessions": self.sessions,
            "is_work": self.is_work,
            "work_dur": self.work_dur,
            "break_dur": self.break_dur,
            "long_break": self.long_break,
            "start_t": self.start_t,
            "paused_state": self.paused_state,
            "timestamp": time.time(),
            "total_duration": self.get_total_duration()
        }
    
    def sync_from_client(self, client_state: dict):
        """Синхронизация состояния с клиента"""
        if client_state.get("state") == "stopped":
            return
        
        # Восстанавливаем состояние
        self.state = client_state.get("state", "stopped")
        self.sessions = client_state.get("sessions", 0)
        self.is_work = client_state.get("is_work", True)
        self.work_dur = client_state.get("work_dur", 1500)
        self.remaining = client_state.get("remaining", self.work_dur)
        self.paused_state = client_state.get("paused_state")
        
        # Корректируем время с учетом задержки
        client_timestamp = client_state.get("timestamp", 0)
        delay = time.time() - client_timestamp
        
        if self.state in ["working", "break"]:
            client_start = client_state.get("start_t")
            if client_start:
                self.start_t = client_start + delay
                # Учитываем, что таймер тикал во время передачи
                self.remaining = max(0, client_state.get("remaining", 0) - delay)
            else:
                self.start_t = time.time()
        
        self._notify()
    
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
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Index file not found</h1>", status_code=404)


@app.get("/manifest.json")
async def manifest():
    manifest = {
        "name": "Pomodoro Timer",
        "short_name": "Pomodoro",
        "description": "Многопользовательский Pomodoro таймер с офлайн-режимом",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#00ffcc",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }
    return manifest


@app.get("/sw.js")
async def service_worker():
    sw_content = """
const CACHE_NAME = 'pomodoro-timer-v2';
const ASSETS_TO_CACHE = [
    '/',
    '/static/index.html',
    '/static/icon-192.png',
    '/static/icon-512.png',
    '/manifest.json'
];

// Установка Service Worker
self.addEventListener('install', (event) => {
    console.log('Service Worker: Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Service Worker: Caching files');
                return cache.addAll(ASSETS_TO_CACHE);
            })
            .then(() => {
                console.log('Service Worker: Skip waiting');
                return self.skipWaiting();
            })
    );
});

// Активация Service Worker
self.addEventListener('activate', (event) => {
    console.log('Service Worker: Activating...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cache) => {
                    if (cache !== CACHE_NAME) {
                        console.log('Service Worker: Clearing old cache');
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

// Перехват запросов
self.addEventListener('fetch', (event) => {
    // Не кэшируем WebSocket соединения
    if (event.request.url.includes('/ws') || event.request.url.includes('/api/sync')) {
        return;
    }
    
    event.respondWith(
        caches.match(event.request)
            .then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                
                return fetch(event.request)
                    .then((response) => {
                        if (response && response.status === 200) {
                            const responseClone = response.clone();
                            caches.open(CACHE_NAME)
                                .then((cache) => {
                                    cache.put(event.request, responseClone);
                                });
                        }
                        return response;
                    })
                    .catch(() => {
                        if (event.request.mode === 'navigate') {
                            return caches.match('/');
                        }
                        return null;
                    });
            })
    );
});

// Обработка сообщений от клиента
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// Обработка push-уведомлений
self.addEventListener('push', (event) => {
    const options = {
        body: event.data ? event.data.text() : 'Время вышло!',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        vibrate: [200, 100, 200],
        tag: 'pomodoro-notification',
        renotify: true,
        actions: [
            { action: 'start', title: 'Старт' },
            { action: 'stop', title: 'Стоп' }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification('Pomodoro Timer', options)
    );
});

// Обработка кликов по уведомлениям
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.matchAll({ type: 'window' })
            .then((clientList) => {
                for (const client of clientList) {
                    if (client.url === '/' && 'focus' in client) {
                        return client.focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow('/');
                }
            })
    );
});
"""
    return HTMLResponse(content=sw_content, media_type="application/javascript")


@app.get("/api/stats")
async def stats():
    return {"active_users": len(active_clients), "max_users": MAX_CLIENTS}


@app.post("/api/sync")
async def sync_state(request: Request):
    """Endpoint для HTTP синхронизации (когда WebSocket недоступен)"""
    try:
        data = await request.json()
        client_id = data.get("client_id")
        client_state = data.get("state")
        
        if client_id and client_id in active_clients:
            client_info = active_clients[client_id]
            timer = client_info["timer"]
            timer.sync_from_client(client_state)
            
            snapshot = timer.get_state_snapshot()
            snapshot["server_time"] = time.time()
            return JSONResponse(snapshot)
        
        return JSONResponse({"error": "Client not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


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
    
    # Генерируем уникальный ID клиента
    client_id = str(id(websocket))
    active_clients[client_id] = {"websocket": websocket, "timer": None}
    
    # Персональный таймер для этого пользователя
    timer = PersonalTimer(client_id)
    active_clients[client_id]["timer"] = timer
    
    # Отправляем начальное состояние с client_id
    m, s = timer.get_time()
    total_dur = timer.get_total_duration()
    
    await websocket.send_json({
        "type": "init",
        "client_id": client_id,
        "timer_update": {
            "type": "timer_update",
            "minutes": m,
            "seconds": s,
            "state": timer.state,
            "sessions": timer.sessions,
            "phase_changed": False,
            "total_duration": total_dur,
            "online": len(active_clients),
            "timestamp": time.time()
        }
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
                            "online": len(active_clients),
                            "timestamp": time.time()
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
                elif action == "sync":
                    # Клиент отправляет свое состояние для синхронизации
                    timer.sync_from_client(cmd.get("timer_state", {}))
                    
                    # Отправляем подтверждение синхронизации
                    snapshot = timer.get_state_snapshot()
                    await websocket.send_json({
                        "type": "sync_confirmed",
                        "server_state": snapshot,
                        "server_time": time.time()
                    })
                    
            except WebSocketDisconnect:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if client_id in active_clients:
            del active_clients[client_id]


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("🍅 Pomodoro Timer - MULTIUSER PWA + OFFLINE")
    print(f"👥 До {MAX_CLIENTS} персональных таймеров")
    print("🔗 ws://host:8000/ws")
    print("📱 PWA с офлайн-режимом")
    print("🔄 Автосинхронизация при восстановлении связи")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")