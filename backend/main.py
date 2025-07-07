# FastAPI backend for multilingual chat translation service
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import json
from typing import Dict, Set, Optional
import asyncio
from datetime import datetime
import logging
import sys
import os

# Import Redis connection manager
from redis_connection_manager import RedisConnectionManager

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

# Global Redis connection manager instance
manager = RedisConnectionManager()

# Response model for room creation
class RoomResponse(BaseModel):
    room_id: str
    created_at: str

# Request model for language detection
class LanguageDetectionRequest(BaseModel):
    text: str

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
    health_data = await manager.health_check()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "redis_status": health_data
    }

# Get room statistics
@app.get("/rooms/{room_id}/stats")
async def get_room_stats(room_id: str):
    try:
        users = await manager.get_room_users(room_id)
        languages = await manager.get_room_languages(room_id)
        message_count = 0
        
        # Get message count from Redis
        try:
            client = await manager._get_redis_client()
            if client:
                message_count = await client.get(f"room:{room_id}:message_count") or 0
                message_count = int(message_count)
        except:
            pass
        
        return {
            "room_id": room_id,
            "active_users": len(users),
            "users": users,
            "languages": list(languages),
            "message_count": message_count,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get room stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room statistics")

# Get global statistics
@app.get("/stats")
async def get_global_stats():
    try:
        room_stats = await manager.get_room_stats()
        
        # Get translation statistics
        from translation_service import translation_service
        translation_stats = await translation_service.get_translation_stats()
        
        return {
            "room_stats": room_stats,
            "translation_stats": translation_stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get global stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get global statistics")

# Get room message history
@app.get("/rooms/{room_id}/history")
async def get_room_history(room_id: str, limit: int = 50):
    try:
        history = await manager.get_message_history(room_id, limit)
        return {
            "room_id": room_id,
            "messages": history,
            "count": len(history),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get room history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room history")

# Redis monitoring dashboard
@app.get("/redis-monitor")
async def redis_monitor():
    try:
        # Get comprehensive Redis information
        health_data = await manager.health_check()
        room_stats = await manager.get_room_stats()
        
        from translation_service import translation_service
        translation_stats = await translation_service.get_translation_stats()
        
        # Get Redis client for additional info
        client = await manager._get_redis_client()
        redis_info = {}
        
        if client:
            # Get all translation cache keys
            cache_keys = await client.keys("translate:*")
            
            # Get all room data
            room_keys = await client.keys("room:*")
            
            # Get rate limit keys
            rate_limit_keys = await client.keys("rate_limit:*")
            
            redis_info = {
                "total_translation_cache_keys": len([k for k in cache_keys if k.startswith("translate:")]),
                "total_room_keys": len([k for k in room_keys if k.startswith("room:")]),
                "active_rate_limits": len(rate_limit_keys),
                "sample_cache_keys": cache_keys[:10] if cache_keys else [],
                "sample_room_keys": room_keys[:10] if room_keys else [],
            }
        
        return {
            "redis_status": "✅ CONNECTED" if health_data.get("redis_connected") else "❌ DISCONNECTED",
            "health": health_data,
            "room_stats": room_stats,
            "translation_stats": translation_stats,
            "redis_data": redis_info,
            "monitoring_time": datetime.now().isoformat(),
            "instructions": {
                "cache_explanation": "🔴 REDIS indicators in logs show real-time Redis operations",
                "log_symbols": {
                    "🔴 REDIS ✅": "Connection established",
                    "🔴 REDIS 🎯": "Cache HIT (translation found in Redis)",
                    "🔴 REDIS 💨": "Cache MISS (translation not in Redis)",
                    "🔴 REDIS 💾": "Data stored in Redis",
                    "🔴 REDIS 👤": "User data stored",
                    "🔴 REDIS 💬": "Message stored in history",
                    "🔴 REDIS 📊": "Statistics updated"
                }
            }
        }
    except Exception as e:
        logger.error(f"Redis monitor error: {e}")
        return {
            "redis_status": "❌ ERROR", 
            "error": str(e),
            "monitoring_time": datetime.now().isoformat()
        }

# Language detection endpoint
@app.post("/detect-language")
async def detect_language(request: dict):
    try:
        text = request.get("text", "")
        if not text.strip():
            return {"language": "en", "confidence": 0.0}
        
        from translation_service import translation_service
        detected_lang = await translation_service.detect_language(text)
        
        return {
            "language": detected_lang,
            "confidence": 1.0,  # Claude doesn't provide confidence scores
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        raise HTTPException(status_code=500, detail="Language detection failed")

# WebSocket endpoint for real-time chat
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # Extract connection parameters from query string
    query_params = websocket.query_params
    client_id = query_params.get("client_id", str(uuid.uuid4()))
    language = query_params.get("language", "en")
    username = query_params.get("username", f"User_{client_id[:8]}")
    
    # Establish connection with Redis support
    await manager.connect(websocket, room_id, client_id, language, username)
    
    # Send recent message history to newly connected user
    try:
        history = await manager.get_message_history(room_id, 10)
        if history:
            await websocket.send_text(json.dumps({
                "type": "history",
                "messages": history[::-1],  # Reverse to show oldest first
                "timestamp": datetime.now().isoformat()
            }))
    except Exception as e:
        logger.warning(f"Failed to send history to {client_id}: {e}")
    
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
            elif message_data.get("type") == "language_change":
                await handle_language_change(room_id, client_id, username, message_data)
                
    except WebSocketDisconnect:
        # Clean up on disconnect
        await manager.disconnect(room_id, client_id)
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
    room_languages = await manager.get_room_languages(room_id)
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
                translated_text = await translate_text(
                    original_text, 
                    target_language, 
                    sender_language, 
                    client_id
                )
                broadcast_message["translations"][target_language] = translated_text
                logger.info(f"Translation successful: '{translated_text}'")
                translation_count += 1
            except Exception as e:
                logger.error(f"Translation error for {target_language}: {e}")
                # Fallback to original text on translation failure
                broadcast_message["translations"][target_language] = original_text
    
    logger.info(f"Total translations made: {translation_count}")
    logger.info(f"Broadcasting message: {broadcast_message}")
    
    # Store message in history
    await manager.store_message(room_id, broadcast_message)
    
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

# Handle language change events
async def handle_language_change(room_id: str, client_id: str, username: str, message_data: dict):
    new_language = message_data.get("language", "en")
    
    # Update user language in Redis
    try:
        client = await manager._get_redis_client()
        if client:
            await client.hset(f"user:{client_id}", "language", new_language)
            await client.hset(f"room:{room_id}:languages", client_id, new_language)
            
            # Update language statistics
            await client.zincrby("popular_languages", 1, new_language)
            
        logger.info(f"User {client_id} changed language to {new_language}")
        
        # Broadcast language change to room
        await manager.broadcast_to_room(room_id, {
            "type": "language_changed",
            "client_id": client_id,
            "username": username,
            "new_language": new_language,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to update language for {client_id}: {e}")

# Startup event to initialize Redis connection
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up translation chat service...")
    # Test Redis connection
    health = await manager.health_check()
    logger.info(f"Redis health: {health}")

# Shutdown event to cleanup connections
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down translation chat service...")
    # Close Redis connections
    if manager.redis_client:
        await manager.redis_client.close()

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)