# FastAPI backend for multilingual chat translation service
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import json
from typing import Dict, Set
import asyncio
from datetime import datetime
import logging

# Configure logging for debugging and monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(title="Translation Chat API", version="1.0.0")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manages WebSocket connections and room state
class ConnectionManager:
    def __init__(self):
        # Store active WebSocket connections by room and client ID
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Track user languages for each room
        self.room_languages: Dict[str, Dict[str, str]] = {}
    
    # Handle new client connection to a room
    async def connect(self, websocket: WebSocket, room_id: str, client_id: str, language: str):
        await websocket.accept()
        
        # Initialize room if it doesn't exist
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
            self.room_languages[room_id] = {}
        
        # Store connection and language preference
        self.active_connections[room_id][client_id] = websocket
        self.room_languages[room_id][client_id] = language
        
        logger.info(f"Client {client_id} connected to room {room_id} with language {language}")
        
        # Notify other users about new connection
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "client_id": client_id,
            "language": language,
            "timestamp": datetime.now().isoformat()
        })
    
    # Handle client disconnection and cleanup
    def disconnect(self, room_id: str, client_id: str):
        if room_id in self.active_connections:
            # Remove client from active connections
            if client_id in self.active_connections[room_id]:
                del self.active_connections[room_id][client_id]
            if client_id in self.room_languages[room_id]:
                del self.room_languages[room_id][client_id]
            
            # Clean up empty rooms
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                del self.room_languages[room_id]
        
        logger.info(f"Client {client_id} disconnected from room {room_id}")
    
    # Send message to all clients in a room
    async def broadcast_to_room(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            disconnected_clients = []
            # Attempt to send to all connected clients
            for client_id, websocket in self.active_connections[room_id].items():
                try:
                    await websocket.send_text(json.dumps(message))
                except:
                    # Mark failed connections for cleanup
                    disconnected_clients.append(client_id)
            
            # Clean up disconnected clients
            for client_id in disconnected_clients:
                self.disconnect(room_id, client_id)
    
    # Get all languages being used in a room
    def get_room_languages(self, room_id: str) -> Set[str]:
        if room_id in self.room_languages:
            return set(self.room_languages[room_id].values())
        return set()

# Global connection manager instance
manager = ConnectionManager()

# Response model for room creation
class RoomResponse(BaseModel):
    room_id: str
    created_at: str

# Create new chat room endpoint
@app.post("/rooms", response_model=RoomResponse)
async def create_room():
    room_id = str(uuid.uuid4())
    return RoomResponse(
        room_id=room_id,
        created_at=datetime.now().isoformat()
    )

# Health check endpoint for monitoring
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# WebSocket endpoint for real-time chat
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # Extract connection parameters from query string
    query_params = websocket.query_params
    client_id = query_params.get("client_id", str(uuid.uuid4()))
    language = query_params.get("language", "en")
    username = query_params.get("username", f"User_{client_id[:8]}")
    
    # Establish connection
    await manager.connect(websocket, room_id, client_id, language)
    
    try:
        # Listen for messages
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Route message types to appropriate handlers
            if message_data.get("type") == "message":
                await handle_message(room_id, client_id, username, language, message_data)
            elif message_data.get("type") == "typing":
                await handle_typing(room_id, client_id, username, message_data)
                
    except WebSocketDisconnect:
        # Clean up on disconnect
        manager.disconnect(room_id, client_id)
        await manager.broadcast_to_room(room_id, {
            "type": "user_left",
            "client_id": client_id,
            "username": username,
            "timestamp": datetime.now().isoformat()
        })

# Handle incoming chat messages and translations
async def handle_message(room_id: str, client_id: str, username: str, sender_language: str, message_data: dict):
    original_text = message_data.get("text", "")
    
    logger.info(f"=== MESSAGE RECEIVED ===")
    logger.info(f"Room: {room_id}, Client: {client_id}, Username: {username}")
    logger.info(f"Sender language: {sender_language}, Text: '{original_text}'")
    
    # Skip empty messages
    if not original_text.strip():
        logger.warning("Empty message received, ignoring")
        return
    
    # Get all languages in the room for translation
    room_languages = manager.get_room_languages(room_id)
    logger.info(f"Room languages: {room_languages}")
    
    # Prepare message structure
    broadcast_message = {
        "type": "message",
        "client_id": client_id,
        "username": username,
        "original_text": original_text,
        "sender_language": sender_language,
        "translations": {},
        "timestamp": datetime.now().isoformat()
    }
    
    # Translate message to all other languages in the room
    translation_count = 0
    for target_language in room_languages:
        if target_language != sender_language:
            logger.info(f"Translating '{original_text}' from {sender_language} to {target_language}")
            try:
                from translation_service import translate_text
                translated_text = await translate_text(original_text, target_language)
                broadcast_message["translations"][target_language] = translated_text
                logger.info(f"Translation successful: '{translated_text}'")
                translation_count += 1
            except Exception as e:
                logger.error(f"Translation error for {target_language}: {e}")
                # Fallback to original text on translation failure
                broadcast_message["translations"][target_language] = original_text
    
    logger.info(f"Total translations made: {translation_count}")
    logger.info(f"Broadcasting message: {broadcast_message}")
    
    # Send translated message to all room participants
    await manager.broadcast_to_room(room_id, broadcast_message)

# Handle typing indicator events
async def handle_typing(room_id: str, client_id: str, username: str, message_data: dict):
    typing_message = {
        "type": "typing",
        "client_id": client_id,
        "username": username,
        "is_typing": message_data.get("is_typing", False),
        "timestamp": datetime.now().isoformat()
    }
    
    # Broadcast typing status to all room participants
    await manager.broadcast_to_room(room_id, typing_message)

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)