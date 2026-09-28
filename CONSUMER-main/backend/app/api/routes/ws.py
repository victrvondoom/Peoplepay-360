from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/cases/{case_id}")
async def case_updates(websocket: WebSocket, case_id: str) -> None:
    await websocket.accept()
    try:
        await websocket.send_json({"type": "connected", "case_id": case_id})
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({"type": "echo", "case_id": case_id, "message": message})
    except WebSocketDisconnect:
        return
