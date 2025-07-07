import asyncio
import json
import logging
import os
from typing import Dict, Set, Optional, Any
from datetime import datetime
import redis.asyncio as redis
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class RedisConnectionManager:
    """Redis-backed WebSocket connection manager for multi-instance deployments"""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.local_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.instance_id = os.getenv("INSTANCE_ID", "default")
        
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client with connection pooling"""
        if self.redis_client is None:
            try:
                self.redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                await self.redis_client.ping()
                logger.info(f"🔴 REDIS ✅ Connection Manager connected for instance {self.instance_id}")
                logger.info(f"Redis connection established for instance {self.instance_id}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None
        return self.redis_client

    async def connect(self, websocket: WebSocket, room_id: str, client_id: str, language: str, username: str = None):
        """Handle new WebSocket connection with Redis state management"""
        await websocket.accept()
        
        # Store local connection
        if room_id not in self.local_connections:
            self.local_connections[room_id] = {}
        self.local_connections[room_id][client_id] = websocket
        
        # Store connection metadata in Redis
        try:
            client = await self._get_redis_client()
            if client:
                # Add user to room
                await client.sadd(f"room:{room_id}:users", client_id)
                
                # Store user metadata
                user_data = {
                    "language": language,
                    "username": username or f"User_{client_id[:8]}",
                    "instance_id": self.instance_id,
                    "connected_at": datetime.now().isoformat()
                }
                await client.hset(f"user:{client_id}", mapping=user_data)
                
                # Store room language mapping
                await client.hset(f"room:{room_id}:languages", client_id, language)
                
                # Update room statistics
                await client.zincrby("room_stats", 1, room_id)
                await client.zincrby("popular_languages", 1, language)
                
                logger.info(f"🔴 REDIS 👤 User {client_id[:8]} stored in Redis:")
                logger.info(f"🔴 REDIS 🏠 Added to room:{room_id}:users")
                logger.info(f"🔴 REDIS 🌍 Language {language} tracked")
                logger.info(f"🔴 REDIS 📊 Stats updated for room and language")
                
                logger.info(f"User {client_id} connected to room {room_id} with language {language}")
                
        except Exception as e:
            logger.error(f"Redis connection storage error: {e}")
        
        # Broadcast user joined event
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "client_id": client_id,
            "username": username or f"User_{client_id[:8]}",
            "language": language,
            "timestamp": datetime.now().isoformat()
        })

    async def disconnect(self, room_id: str, client_id: str):
        """Handle WebSocket disconnection with Redis cleanup"""
        # Remove local connection
        if room_id in self.local_connections:
            if client_id in self.local_connections[room_id]:
                del self.local_connections[room_id][client_id]
            
            # Clean up empty rooms locally
            if not self.local_connections[room_id]:
                del self.local_connections[room_id]
        
        # Clean up Redis data
        try:
            client = await self._get_redis_client()
            if client:
                # Remove user from room
                await client.srem(f"room:{room_id}:users", client_id)
                
                # Remove user metadata
                await client.delete(f"user:{client_id}")
                
                # Remove from room languages
                await client.hdel(f"room:{room_id}:languages", client_id)
                
                # Check if room is empty
                room_users = await client.smembers(f"room:{room_id}:users")
                if not room_users:
                    await client.delete(f"room:{room_id}:languages")
                    await client.delete(f"room:{room_id}:history")
                    logger.info(f"Room {room_id} cleaned up - no users remaining")
                
        except Exception as e:
            logger.error(f"Redis disconnect cleanup error: {e}")
        
        logger.info(f"User {client_id} disconnected from room {room_id}")

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Broadcast message to all users in a room (local connections only)"""
        if room_id in self.local_connections:
            disconnected_clients = []
            
            for client_id, websocket in self.local_connections[room_id].items():
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.warning(f"Failed to send message to {client_id}: {e}")
                    disconnected_clients.append(client_id)
            
            # Clean up failed connections
            for client_id in disconnected_clients:
                await self.disconnect(room_id, client_id)

    async def get_room_languages(self, room_id: str) -> Set[str]:
        """Get all languages being used in a room"""
        try:
            client = await self._get_redis_client()
            if client:
                languages = await client.hvals(f"room:{room_id}:languages")
                return set(languages)
        except Exception as e:
            logger.error(f"Failed to get room languages: {e}")
        
        # Fallback to local data if Redis fails
        if room_id in self.local_connections:
            # This is a simplified fallback - in production you'd want better state management
            return {"en"}  # Default fallback
        return set()

    async def get_room_users(self, room_id: str) -> Dict[str, dict]:
        """Get all users in a room with their metadata"""
        try:
            client = await self._get_redis_client()
            if client:
                user_ids = await client.smembers(f"room:{room_id}:users")
                users = {}
                
                for user_id in user_ids:
                    user_data = await client.hgetall(f"user:{user_id}")
                    if user_data:
                        users[user_id] = user_data
                
                return users
        except Exception as e:
            logger.error(f"Failed to get room users: {e}")
        
        return {}

    async def store_message(self, room_id: str, message: dict, max_history: int = 50):
        """Store message in room history"""
        try:
            client = await self._get_redis_client()
            if client:
                # Add message to room history
                await client.lpush(f"room:{room_id}:history", json.dumps(message))
                # Keep only the last N messages
                await client.ltrim(f"room:{room_id}:history", 0, max_history - 1)
                
                # Update message statistics
                total_messages = await client.incr("total_messages")
                room_messages = await client.incr(f"room:{room_id}:message_count")
                
                logger.info(f"🔴 REDIS 💬 Message stored in history (room: {room_messages}, total: {total_messages})")
                logger.info(f"🔴 REDIS 📝 Room {room_id} history updated (max {max_history} messages)")
                
        except Exception as e:
            logger.error(f"Failed to store message: {e}")

    async def get_message_history(self, room_id: str, limit: int = 20) -> list:
        """Get recent message history for a room"""
        try:
            client = await self._get_redis_client()
            if client:
                messages = await client.lrange(f"room:{room_id}:history", 0, limit - 1)
                return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Failed to get message history: {e}")
        
        return []

    async def get_room_stats(self) -> Dict[str, Any]:
        """Get comprehensive room statistics"""
        try:
            client = await self._get_redis_client()
            if client:
                # Get top rooms by activity
                top_rooms = await client.zrevrange("room_stats", 0, 9, withscores=True)
                
                # Get total active rooms
                active_rooms = await client.keys("room:*:users")
                
                # Get total messages
                total_messages = await client.get("total_messages") or "0"
                
                # Get popular languages
                popular_languages = await client.zrevrange("popular_languages", 0, 9, withscores=True)
                
                return {
                    "active_rooms": len(active_rooms),
                    "total_messages": int(total_messages),
                    "top_rooms": dict(top_rooms) if top_rooms else {},
                    "popular_languages": dict(popular_languages) if popular_languages else {},
                    "local_connections": sum(len(conns) for conns in self.local_connections.values())
                }
        except Exception as e:
            logger.error(f"Failed to get room stats: {e}")
        
        return {"error": "Redis unavailable"}

    async def cleanup_stale_connections(self, max_age_hours: int = 24):
        """Clean up stale user connections"""
        try:
            client = await self._get_redis_client()
            if client:
                # This would need more sophisticated implementation
                # For now, just log that cleanup is needed
                logger.info("Stale connection cleanup would run here")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Health check for Redis connection and service status"""
        try:
            client = await self._get_redis_client()
            if client:
                start_time = datetime.now()
                await client.ping()
                latency = (datetime.now() - start_time).total_seconds() * 1000
                
                return {
                    "redis_connected": True,
                    "redis_latency_ms": round(latency, 2),
                    "local_connections": sum(len(conns) for conns in self.local_connections.values()),
                    "instance_id": self.instance_id,
                    "status": "healthy"
                }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
        
        return {
            "redis_connected": False,
            "local_connections": sum(len(conns) for conns in self.local_connections.values()),
            "instance_id": self.instance_id,
            "status": "degraded"
        }