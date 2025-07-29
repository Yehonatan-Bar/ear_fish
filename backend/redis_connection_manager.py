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
    """
    Redis-backed WebSocket connection manager for multi-instance deployments.
    
    This manager handles WebSocket connections in a distributed environment,
    allowing multiple server instances to share connection state via Redis.
    
    Key features:
    - Distributed connection tracking across multiple server instances
    - Room-based message broadcasting
    - User metadata and language preference storage
    - Message history persistence
    - Connection health monitoring
    - Automatic cleanup of stale connections
    
    Libraries used:
        - redis.asyncio: For distributed state management
        - FastAPI WebSocket: For real-time client connections
        - json: For message serialization
        - logging: For operation tracking
    """
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.local_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.local_user_languages: Dict[str, Dict[str, str]] = {}  # room_id -> {client_id: language}
        self.instance_id = os.getenv("INSTANCE_ID", "default")
        
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """
        Creates a new Redis client connection for each operation.
        
        This method creates fresh connections to avoid connection pooling issues
        and potential recursion problems. Each connection is configured with:
        - Short timeouts (2s) for fast failure detection
        - Automatic retry on timeout
        - Health check intervals for connection monitoring
        
        Returns:
            Optional[redis.Redis]: Connected Redis client or None if connection fails
        
        Note:
            Connections should always be closed after use to prevent leaks.
        """
        try:
            client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                retry_on_timeout=True,
                health_check_interval=30
            )
            await client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    async def connect(self, websocket: WebSocket, room_id: str, client_id: str, language: str, username: str = None):
        """
        Handles new WebSocket connections and syncs state to Redis.
        
        This method performs several operations when a user connects:
        1. Accepts the WebSocket connection
        2. Stores connection in local memory for this instance
        3. Persists user metadata to Redis for cross-instance access
        4. Updates room membership and statistics
        5. Broadcasts join event to all room participants
        
        Redis operations performed:
        - SADD: Add user to room set
        - HSET: Store user metadata (language, username, timestamp)
        - ZINCRBY: Update room and language statistics
        
        Args:
            websocket: FastAPI WebSocket connection
            room_id: Unique room identifier
            client_id: Unique client identifier
            language: User's preferred language code
            username: Optional display name
        
        Emoji indicators in logs:
            🔴 REDIS 👤: User data stored
            🔴 REDIS 🏠: Room membership updated
            🔴 REDIS 🌍: Language preference tracked
            🔴 REDIS 📊: Statistics updated
        """
        await websocket.accept()
        
        # Store local connection
        if room_id not in self.local_connections:
            self.local_connections[room_id] = {}
        self.local_connections[room_id][client_id] = websocket
        
        # Store local language mapping
        if room_id not in self.local_user_languages:
            self.local_user_languages[room_id] = {}
        self.local_user_languages[room_id][client_id] = language
        
        # Store connection metadata in Redis
        client = None
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
        finally:
            if client:
                await client.close()
        
        # Broadcast user joined event
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "client_id": client_id,
            "username": username or f"User_{client_id[:8]}",
            "language": language,
            "timestamp": datetime.now().isoformat()
        })

    async def disconnect(self, room_id: str, client_id: str):
        """
        Handles WebSocket disconnections and cleans up Redis state.
        
        This method ensures proper cleanup when a user disconnects:
        1. Removes connection from local memory
        2. Cleans up user data from Redis
        3. Updates room membership
        4. Deletes empty rooms to prevent memory leaks
        
        Redis operations performed:
        - SREM: Remove user from room set
        - DELETE: Remove user metadata
        - HDEL: Remove from room language mapping
        - Conditional DELETE: Remove empty room data
        
        Args:
            room_id: Room the user is leaving
            client_id: Disconnecting client's identifier
        
        Note:
            Empty rooms are automatically cleaned up to prevent
            Redis memory bloat from abandoned rooms.
        """
        # Remove local connection
        if room_id in self.local_connections:
            if client_id in self.local_connections[room_id]:
                del self.local_connections[room_id][client_id]
            
            # Clean up empty rooms locally
            if not self.local_connections[room_id]:
                del self.local_connections[room_id]
        
        # Remove local language mapping
        if room_id in self.local_user_languages:
            if client_id in self.local_user_languages[room_id]:
                del self.local_user_languages[room_id][client_id]
            
            # Clean up empty rooms
            if not self.local_user_languages[room_id]:
                del self.local_user_languages[room_id]
        
        # Clean up Redis data
        client = None
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
        finally:
            if client:
                await client.close()
        
        logger.info(f"User {client_id} disconnected from room {room_id}")

    async def broadcast_to_room(self, room_id: str, message: dict):
        """
        Broadcasts a message to all WebSocket connections in a room.
        
        This method sends messages only to connections managed by this
        server instance (local connections). In a multi-instance deployment,
        each instance handles its own connections.
        
        Features:
        - Automatic detection and cleanup of failed connections
        - JSON serialization of message data
        - Graceful error handling for network issues
        
        Args:
            room_id: Target room for broadcast
            message: Dictionary containing message data
        
        Note:
            Failed connections are automatically disconnected and cleaned up
            to maintain connection list integrity.
        """
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
        """
        Retrieves all unique languages being used in a chat room.
        
        This method is crucial for the translation system as it determines
        which languages need translations. It:
        1. Queries Redis for the authoritative language list
        2. Falls back to local data if Redis is unavailable
        3. Returns a set of unique language codes
        
        Returns:
            Set[str]: Unique language codes (e.g., {'en', 'es', 'fr'})
        
        Fallback behavior:
            If Redis is unavailable, uses local instance data which may
            be incomplete in multi-instance deployments.
        
        Libraries used:
            - Redis HVALS: To get all values from language hash
        """
        client = None
        try:
            client = await self._get_redis_client()
            if client:
                languages = await client.hvals(f"room:{room_id}:languages")
                if languages:
                    return set(languages)
        except Exception as e:
            logger.error(f"Failed to get room languages from Redis: {e}")
        finally:
            if client:
                await client.close()
        
        # Fallback to local data if Redis fails
        if room_id in self.local_user_languages:
            languages = set(self.local_user_languages[room_id].values())
            logger.info(f"Using local language data for room {room_id}: {languages}")
            return languages
        
        logger.warning(f"No language data found for room {room_id}")
        return set()

    async def get_room_users(self, room_id: str) -> Dict[str, dict]:
        """
        Retrieves all users in a room with their complete metadata.
        
        This method provides a comprehensive view of room participants by:
        1. Getting user IDs from the room membership set
        2. Fetching detailed metadata for each user
        3. Returning a dictionary mapping user IDs to their data
        
        User metadata includes:
        - language: User's preferred language
        - username: Display name
        - instance_id: Server instance handling the connection
        - connected_at: Connection timestamp
        
        Returns:
            Dict[str, dict]: Mapping of user_id to user metadata
        
        Redis operations:
            - SMEMBERS: Get all user IDs in room
            - HGETALL: Get user metadata for each ID
        """
        client = None
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
        finally:
            if client:
                await client.close()
        
        return {}

    async def store_message(self, room_id: str, message: dict, max_history: int = 50):
        """
        Stores a message in the room's persistent history.
        
        This method maintains a rolling history of messages for each room,
        allowing users to see recent messages when joining. It:
        1. Adds new messages to the front of the list (LIFO)
        2. Maintains a maximum history size to prevent memory bloat
        3. Updates message count statistics
        
        Args:
            room_id: Room to store message in
            message: Complete message data including translations
            max_history: Maximum messages to keep (default: 50)
        
        Redis operations:
            - LPUSH: Add message to history list
            - LTRIM: Keep only the most recent N messages
            - INCR: Update message counters
        
        Emoji indicators:
            🔴 REDIS 💬: Message stored in history
            🔴 REDIS 📝: History trimmed to size limit
        """
        client = None
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
        finally:
            if client:
                await client.close()

    async def get_message_history(self, room_id: str, limit: int = 20) -> list:
        """
        Retrieves recent message history for a room.
        
        This method fetches stored messages from Redis, typically used when:
        - New users join a room and need context
        - Users refresh the page
        - Loading conversation history
        
        Messages are returned in reverse chronological order (newest first).
        
        Args:
            room_id: Room to get history for
            limit: Maximum messages to retrieve (default: 20)
        
        Returns:
            list: List of message dictionaries with all translations
        
        Redis operations:
            - LRANGE: Get range of messages from history list
        """
        client = None
        try:
            client = await self._get_redis_client()
            if client:
                messages = await client.lrange(f"room:{room_id}:history", 0, limit - 1)
                return [json.loads(msg) for msg in messages]
        except Exception as e:
            logger.error(f"Failed to get message history: {e}")
        finally:
            if client:
                await client.close()
        
        return []

    async def get_room_stats(self) -> Dict[str, Any]:
        """
        Gathers comprehensive statistics about all chat rooms.
        
        This method collects system-wide metrics including:
        - Active room count
        - Total messages sent
        - Most active rooms (by join count)
        - Popular languages
        - Current connection count for this instance
        
        These statistics are useful for:
        - Monitoring system health and usage
        - Identifying popular rooms
        - Understanding language distribution
        - Capacity planning
        
        Returns:
            Dict containing:
            - active_rooms: Number of rooms with users
            - total_messages: Global message count
            - top_rooms: Top 10 rooms by activity
            - popular_languages: Top 10 languages by usage
            - local_connections: Connections on this instance
        
        Redis operations:
            - ZREVRANGE: Get top items from sorted sets
            - KEYS: Count active room keys
            - GET: Retrieve counter values
        """
        client = None
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
        finally:
            if client:
                await client.close()
        
        return {"error": "Redis unavailable"}

    async def cleanup_stale_connections(self, max_age_hours: int = 24):
        """
        Cleans up stale connections from crashed instances or network failures.
        
        This method would typically:
        - Identify connections older than max_age_hours
        - Remove stale user data and room memberships
        - Clean up orphaned rooms
        
        Args:
            max_age_hours: Maximum age before considering connection stale
        
        Note:
            Current implementation is a placeholder. A full implementation
            would check connection timestamps and remove outdated entries.
        
        TODO:
            Implement timestamp checking and cleanup logic
        """
        client = None
        try:
            client = await self._get_redis_client()
            if client:
                # This would need more sophisticated implementation
                # For now, just log that cleanup is needed
                logger.info("Stale connection cleanup would run here")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        finally:
            if client:
                await client.close()

    async def health_check(self) -> Dict[str, Any]:
        """
        Performs comprehensive health check of the connection manager.
        
        This method checks:
        - Redis connectivity and response time
        - Local connection count
        - Instance identification
        - Overall service health status
        
        Health states:
        - "healthy": Redis connected, low latency
        - "degraded": Redis unavailable, using local fallbacks
        
        Returns:
            Dict containing:
            - redis_connected: Boolean connection status
            - redis_latency_ms: Round-trip time to Redis
            - local_connections: Active WebSocket count
            - instance_id: Server instance identifier
            - status: Overall health state
        
        Used by:
            - Load balancers for health checks
            - Monitoring systems
            - Debugging connection issues
        """
        client = None
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
        finally:
            if client:
                await client.close()
        
        return {
            "redis_connected": False,
            "local_connections": sum(len(conns) for conns in self.local_connections.values()),
            "instance_id": self.instance_id,
            "status": "degraded"
        }