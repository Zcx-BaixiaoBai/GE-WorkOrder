"""金鹰工单KPI管理 - WebSocket实时通知"""
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List

router = APIRouter()


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


manager = ConnectionManager()


@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点：实时推送同步进度"""
    await manager.connect(websocket)
    try:
        while True:
            # 保持连接，接收客户端心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "get_status":
                from backend.services.sync_service import SyncService
                status = SyncService.get_sync_status()
                await websocket.send_json({"type": "sync_status", "data": status})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def notify_sync_progress(progress: int, message: str):
    """广播同步进度"""
    await manager.broadcast({
        "type": "sync_progress",
        "progress": progress,
        "message": message,
    })


async def notify_sync_complete(result: dict):
    """广播同步完成"""
    await manager.broadcast({
        "type": "sync_complete",
        "data": result,
    })


async def notify_warning(data: dict):
    """广播预警通知"""
    await manager.broadcast({
        "type": "warning",
        "data": data,
    })
