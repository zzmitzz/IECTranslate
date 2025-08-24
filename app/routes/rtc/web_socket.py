import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional, Dict
from app.routes.rtc.web_rtc import WebRTCHandler
from app.auth.dependencies import verify_api_key
from app.config import API_KEY_HEADER_NAME, API_KEY

logger = logging.getLogger(__name__)

websocket_router = APIRouter()

# API key header for WebSocket authentication
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.webrtc_handler = WebRTCHandler()
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected")
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected")
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")

# Global connection manager instance
manager = ConnectionManager()

async def verify_websocket_api_key(websocket: WebSocket) -> bool:
    """Verify API key from WebSocket headers"""
    try:
        # Get API key from query parameters or headers
        api_key = websocket.query_params.get("api_key") or websocket.headers.get(API_KEY_HEADER_NAME)
        
        # Debug logging
        logger.info(f"WebSocket connection attempt - API key provided: {bool(api_key)}")
        logger.info(f"Expected API key: {API_KEY[:8]}..." if API_KEY else "None")
        logger.info(f"Received API key: {api_key[:8]}..." if api_key else "None")
        
        if not api_key:
            logger.warning("No API key provided in WebSocket connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing API key")
            return False
        
        # Verify API key
        if api_key != API_KEY:
            logger.warning(f"Invalid API key provided: {api_key[:8]}...")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid API key")
            return False
        
        logger.info("API key verification successful")
        return True
    except Exception as e:
        logger.error(f"Error verifying API key: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Authentication error")
        return False

@websocket_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time communication and WebRTC signaling"""
    
    # Verify API key before accepting connection
    if not await verify_websocket_api_key(websocket):
        return
    
    try:
        # Accept the WebSocket connection
        await manager.connect(websocket, user_id)
        logger.info(f"WebSocket connection established for user: {user_id}")
        # Send connection confirmation
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "user_id": user_id,
                "status": "connected"
            }), 
            user_id
        )
        
        # Handle incoming messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                logger.info(f"Received message: {message}")
                # Handle different message types
                await handle_websocket_message(message, user_id)
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from user {user_id}")
                await manager.send_personal_message(
                    json.dumps({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }), 
                    user_id
                )
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Error in WebSocket connection for user {user_id}: {e}")
        manager.disconnect(user_id)

async def handle_websocket_message(message: dict, user_id: str):
    """Handle different types of WebSocket messages"""
    
    print("hello", message)
    message_type = message.get("type")
    logger.info(f"Received message: {message_type}")
    try:
        if message_type == "offer":
            # Handle WebRTC offer
            room_id = message.get("roomId")
            offer = message.get("offer")
            
            if not room_id or not offer:
                raise ValueError("Missing roomId or offer")
            
            # Create peer connection and handle offer
            answer = await manager.webrtc_handler.handle_offer(room_id, user_id, offer)
            
            # Send answer back to client
            await manager.send_personal_message(
                json.dumps({
                    "type": "answer",
                    "roomId": room_id,
                    "answer": answer
                }), 
                user_id
            )
            
        elif message_type == "answer":
            # Handle WebRTC answer
            answer = message.get("answer")
            if answer:
                await manager.webrtc_handler.handle_answer(user_id, answer)
                
        elif message_type == "ice-candidate":
            # Handle WebRTC ICE candidate
            room_id = message.get("roomId")
            candidate = message.get("candidate")
            
            if room_id and candidate:
                await manager.webrtc_handler.handle_candidate(room_id, user_id, candidate)
                
        elif message_type == "join-room":
            # Handle room joining
            room_id = message.get("roomId")
            if room_id:
                # Join the WebRTC room (not async)
                manager.webrtc_handler.room.join(room_id, user_id)
                
                await manager.send_personal_message(
                    json.dumps({
                        "type": "room-joined",
                        "roomId": room_id,
                        "peerId": user_id
                    }), 
                    user_id
                )
                
                # Notify other users in the room
                await manager.broadcast(
                    json.dumps({
                        "type": "user-joined-room",
                        "roomId": room_id,
                        "peerId": user_id
                    })
                )
                
        elif message_type == "leave-room":
            # Handle room leaving
            room_id = message.get("roomId")
            if room_id:
                # Leave the WebRTC room (not async)
                manager.webrtc_handler.room.leave(user_id)
                
                await manager.send_personal_message(
                    json.dumps({
                        "type": "room-left",
                        "roomId": room_id,
                        "peerId": user_id
                    }), 
                    user_id
                )
                
                # Notify other users in the room
                await manager.broadcast(
                    json.dumps({
                        "type": "user-left-room",
                        "roomId": room_id,
                        "peerId": user_id
                    })
                )
                
        elif message_type == "ping":
            # Handle ping for connection health check
            await manager.send_personal_message(
                json.dumps({
                    "type": "pong",
                    "timestamp": message.get("timestamp")
                }), 
                user_id
            )
            
        else:
            # Unknown message type
            logger.warning(f"Unknown message type '{message_type}' from user {user_id}")
            await manager.send_personal_message(
                json.dumps({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                }), 
                user_id
            )
            
    except Exception as e:
        logger.error(f"Error handling message from user {user_id}: {e}")
        await manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": f"Error processing message: {str(e)}"
            }), 
            user_id
        )

@websocket_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_connections": len(manager.active_connections),
        "active_rooms": len(manager.webrtc_handler.room.rooms)
    }

@websocket_router.get("/connections")
async def get_connections():
    """Get current active connections"""
    return {
        "active_connections": list(manager.active_connections.keys()),
        "total_connections": len(manager.active_connections)
    }

