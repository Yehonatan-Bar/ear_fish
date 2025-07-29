import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisUtils:
    """
    Utility class for common Redis operations across the application.
    
    This class provides a comprehensive set of safe, error-handled Redis operations
    with connection pooling for optimal performance. It serves as a wrapper around
    redis.asyncio to ensure all operations handle failures gracefully.
    
    Key features:
    - Connection pooling for efficient resource usage
    - Automatic error handling with fallback values
    - Comprehensive logging of failures
    - Support for all major Redis data structures
    - Health monitoring and statistics
    
    Libraries used:
        - redis.asyncio: For asynchronous Redis operations
        - logging: For error and warning tracking
        - datetime: For timestamp and timing operations
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client = None
        self._connection_pool = None
        
    async def get_client(self) -> Optional[redis.Redis]:
        """
        Gets or creates a Redis client with connection pooling.
        
        This method implements a singleton pattern for the Redis client,
        creating a connection pool on first use and reusing it for all
        subsequent operations. The connection pool provides:
        - Efficient connection reuse
        - Automatic connection retry
        - Configurable connection limits
        
        Connection pool settings:
        - max_connections: 20 (handles concurrent operations)
        - socket_timeout: 5s (operation timeout)
        - retry_on_timeout: True (automatic retry)
        
        Returns:
            Optional[redis.Redis]: Connected client or None if connection fails
        
        Libraries used:
            - redis.ConnectionPool: For connection management
        """
        if self._client is None:
            try:
                self._connection_pool = redis.ConnectionPool.from_url(
                    self.redis_url,
                    decode_responses=True,
                    max_connections=20,
                    socket_timeout=5.0,
                    socket_connect_timeout=5.0,
                    retry_on_timeout=True
                )
                self._client = redis.Redis(connection_pool=self._connection_pool)
                await self._client.ping()
                logger.info("Redis connection pool established")
            except Exception as e:
                logger.error(f"Failed to establish Redis connection: {e}")
                self._client = None
        return self._client
    
    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._connection_pool:
            await self._connection_pool.disconnect()
            self._connection_pool = None
    
    async def safe_get(self, key: str, default: Any = None) -> Any:
        """
        Safely retrieves a value from Redis with automatic error handling.
        
        This wrapper around Redis GET operation ensures:
        - No exceptions propagate to calling code
        - Default value returned on any failure
        - Errors are logged for debugging
        
        Common use cases:
        - Cache lookups
        - Configuration retrieval
        - Counter values
        
        Args:
            key: Redis key to retrieve
            default: Value to return if key missing or error occurs
        
        Returns:
            Any: Retrieved value or default
        """
        try:
            client = await self.get_client()
            if client:
                result = await client.get(key)
                return result if result is not None else default
        except Exception as e:
            logger.warning(f"Redis get error for key {key}: {e}")
        return default
    
    async def safe_set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Safely stores a value in Redis with optional expiration.
        
        This wrapper provides:
        - Automatic error handling
        - Optional TTL (Time To Live) support
        - Success/failure indication
        
        Common use cases:
        - Cache storage
        - Session data
        - Temporary locks
        
        Args:
            key: Redis key to store under
            value: Value to store (automatically serialized)
            ttl: Optional expiration time in seconds
        
        Returns:
            bool: True if successful, False on error
        """
        try:
            client = await self.get_client()
            if client:
                if ttl:
                    await client.setex(key, ttl, value)
                else:
                    await client.set(key, value)
                return True
        except Exception as e:
            logger.warning(f"Redis set error for key {key}: {e}")
        return False
    
    async def safe_delete(self, *keys: str) -> bool:
        """Safely delete keys from Redis"""
        try:
            client = await self.get_client()
            if client:
                await client.delete(*keys)
                return True
        except Exception as e:
            logger.warning(f"Redis delete error for keys {keys}: {e}")
        return False
    
    async def safe_incr(self, key: str, amount: int = 1, ttl: int = None) -> Optional[int]:
        """
        Safely increments a counter with automatic TTL on first use.
        
        This atomic operation is perfect for:
        - Rate limiting counters
        - Statistics tracking
        - Sequence generation
        
        Special behavior:
        - Creates counter if it doesn't exist
        - Sets TTL only on first increment (when counter equals amount)
        - Returns None on error (allows graceful degradation)
        
        Args:
            key: Counter key
            amount: Increment value (default: 1)
            ttl: Optional expiration for new counters
        
        Returns:
            Optional[int]: New counter value or None on error
        """
        try:
            client = await self.get_client()
            if client:
                result = await client.incr(key, amount)
                if ttl and result == amount:  # First increment, set TTL
                    await client.expire(key, ttl)
                return result
        except Exception as e:
            logger.warning(f"Redis incr error for key {key}: {e}")
        return None
    
    async def safe_hget(self, key: str, field: str, default: Any = None) -> Any:
        """
        Safely retrieves a field from a Redis hash.
        
        Redis hashes are ideal for storing objects or related data.
        This method safely gets a single field value.
        
        Common use cases:
        - User profile fields
        - Configuration settings
        - Object properties
        
        Args:
            key: Hash key
            field: Field name within the hash
            default: Value if field missing or error
        
        Returns:
            Any: Field value or default
        """
        try:
            client = await self.get_client()
            if client:
                result = await client.hget(key, field)
                return result if result is not None else default
        except Exception as e:
            logger.warning(f"Redis hget error for key {key}, field {field}: {e}")
        return default
    
    async def safe_hset(self, key: str, field: str = None, value: Any = None, mapping: Dict = None) -> bool:
        """
        Safely sets one or more fields in a Redis hash.
        
        Supports two modes:
        1. Single field: Provide field and value
        2. Multiple fields: Provide mapping dictionary
        
        Common use cases:
        - Updating user profiles
        - Storing object state
        - Batch updates
        
        Args:
            key: Hash key
            field: Single field name (mode 1)
            value: Single field value (mode 1)
            mapping: Dict of field:value pairs (mode 2)
        
        Returns:
            bool: True if successful, False on error
        """
        try:
            client = await self.get_client()
            if client:
                if mapping:
                    await client.hset(key, mapping=mapping)
                else:
                    await client.hset(key, field, value)
                return True
        except Exception as e:
            logger.warning(f"Redis hset error for key {key}: {e}")
        return False
    
    async def safe_hgetall(self, key: str) -> Dict[str, Any]:
        """Safely get all hash fields from Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.hgetall(key)
        except Exception as e:
            logger.warning(f"Redis hgetall error for key {key}: {e}")
        return {}
    
    async def safe_lpush(self, key: str, *values: Any) -> Optional[int]:
        """
        Safely pushes values to the head of a Redis list.
        
        Lists in Redis are ideal for:
        - Message queues
        - Activity feeds
        - History logs
        
        Values are added to the beginning (left side) of the list,
        making this perfect for LIFO (Last In, First Out) patterns.
        
        Args:
            key: List key
            *values: One or more values to push
        
        Returns:
            Optional[int]: New list length or None on error
        """
        try:
            client = await self.get_client()
            if client:
                return await client.lpush(key, *values)
        except Exception as e:
            logger.warning(f"Redis lpush error for key {key}: {e}")
        return None
    
    async def safe_lrange(self, key: str, start: int, end: int) -> List[Any]:
        """
        Safely retrieves a range of values from a Redis list.
        
        List indices work like Python:
        - 0 is first element
        - -1 is last element
        - Range is inclusive
        
        Common patterns:
        - Get first 10: lrange(key, 0, 9)
        - Get last 5: lrange(key, -5, -1)
        - Get all: lrange(key, 0, -1)
        
        Args:
            key: List key
            start: Start index (inclusive)
            end: End index (inclusive)
        
        Returns:
            List[Any]: List values or empty list on error
        """
        try:
            client = await self.get_client()
            if client:
                return await client.lrange(key, start, end)
        except Exception as e:
            logger.warning(f"Redis lrange error for key {key}: {e}")
        return []
    
    async def safe_ltrim(self, key: str, start: int, end: int) -> bool:
        """Safely trim list in Redis"""
        try:
            client = await self.get_client()
            if client:
                await client.ltrim(key, start, end)
                return True
        except Exception as e:
            logger.warning(f"Redis ltrim error for key {key}: {e}")
        return False
    
    async def safe_sadd(self, key: str, *values: Any) -> Optional[int]:
        """
        Safely adds values to a Redis set.
        
        Sets provide unique value storage, perfect for:
        - User groups/roles
        - Tags or categories
        - Unique visitor tracking
        
        Duplicate values are automatically ignored by Redis.
        
        Args:
            key: Set key
            *values: One or more values to add
        
        Returns:
            Optional[int]: Number of values actually added or None
        """
        try:
            client = await self.get_client()
            if client:
                return await client.sadd(key, *values)
        except Exception as e:
            logger.warning(f"Redis sadd error for key {key}: {e}")
        return None
    
    async def safe_srem(self, key: str, *values: Any) -> Optional[int]:
        """Safely remove values from set in Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.srem(key, *values)
        except Exception as e:
            logger.warning(f"Redis srem error for key {key}: {e}")
        return None
    
    async def safe_smembers(self, key: str) -> set:
        """Safely get all set members from Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.smembers(key)
        except Exception as e:
            logger.warning(f"Redis smembers error for key {key}: {e}")
        return set()
    
    async def safe_zincrby(self, key: str, amount: float, value: Any) -> Optional[float]:
        """
        Safely increments a score in a Redis sorted set.
        
        Sorted sets are perfect for:
        - Leaderboards
        - Popular items tracking
        - Time-series data with scores
        
        If the value doesn't exist, it's created with the given score.
        
        Args:
            key: Sorted set key
            amount: Score increment (can be negative)
            value: Member to update
        
        Returns:
            Optional[float]: New score or None on error
        """
        try:
            client = await self.get_client()
            if client:
                return await client.zincrby(key, amount, value)
        except Exception as e:
            logger.warning(f"Redis zincrby error for key {key}: {e}")
        return None
    
    async def safe_zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> List[Any]:
        """
        Safely retrieves members from a sorted set in descending score order.
        
        This is the go-to method for:
        - Top N leaderboards
        - Most popular items
        - Highest scores
        
        Examples:
        - Top 10: zrevrange(key, 0, 9)
        - Top 100 with scores: zrevrange(key, 0, 99, withscores=True)
        
        Args:
            key: Sorted set key
            start: Start rank (0 = highest score)
            end: End rank (inclusive)
            withscores: Include scores in result
        
        Returns:
            List: Members (and optionally scores) or empty list
        """
        try:
            client = await self.get_client()
            if client:
                return await client.zrevrange(key, start, end, withscores=withscores)
        except Exception as e:
            logger.warning(f"Redis zrevrange error for key {key}: {e}")
        return []
    
    async def safe_expire(self, key: str, seconds: int) -> bool:
        """Safely set expiration for key in Redis"""
        try:
            client = await self.get_client()
            if client:
                await client.expire(key, seconds)
                return True
        except Exception as e:
            logger.warning(f"Redis expire error for key {key}: {e}")
        return False
    
    async def safe_ttl(self, key: str) -> Optional[int]:
        """Safely get TTL for key in Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.ttl(key)
        except Exception as e:
            logger.warning(f"Redis ttl error for key {key}: {e}")
        return None
    
    async def safe_exists(self, *keys: str) -> Optional[int]:
        """Safely check if keys exist in Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.exists(*keys)
        except Exception as e:
            logger.warning(f"Redis exists error for keys {keys}: {e}")
        return None
    
    async def safe_keys(self, pattern: str = "*") -> List[str]:
        """
        Safely retrieves keys matching a pattern.
        
        WARNING: KEYS command can be slow on large databases.
        Use SCAN for production systems with many keys.
        
        Pattern syntax:
        - * matches any characters
        - ? matches single character
        - [abc] matches a, b, or c
        
        Examples:
        - "user:*" - all user keys
        - "cache:????" - cache keys with 4 chars
        
        Args:
            pattern: Match pattern (default: all keys)
        
        Returns:
            List[str]: Matching keys or empty list
        """
        try:
            client = await self.get_client()
            if client:
                return await client.keys(pattern)
        except Exception as e:
            logger.warning(f"Redis keys error for pattern {pattern}: {e}")
        return []
    
    async def safe_scan(self, cursor: int = 0, match: str = None, count: int = None) -> tuple:
        """
        Safely scans Redis keys without blocking the server.
        
        SCAN is the production-safe alternative to KEYS, providing:
        - Non-blocking iteration
        - Cursor-based pagination
        - Pattern matching support
        
        Usage pattern:
        ```python
        cursor = 0
        while True:
            cursor, keys = await safe_scan(cursor, match="user:*")
            # Process keys
            if cursor == 0:
                break
        ```
        
        Args:
            cursor: Iteration cursor (0 to start)
            match: Optional pattern filter
            count: Hint for number of keys per iteration
        
        Returns:
            tuple: (next_cursor, keys) or (0, []) on error
        """
        try:
            client = await self.get_client()
            if client:
                return await client.scan(cursor=cursor, match=match, count=count)
        except Exception as e:
            logger.warning(f"Redis scan error: {e}")
        return (0, [])
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """
        Retrieves comprehensive Redis memory usage statistics.
        
        This method provides insights into:
        - Current memory usage
        - Peak memory usage
        - System memory availability
        - Memory fragmentation (indicator of efficiency)
        
        Use this for:
        - Monitoring Redis health
        - Capacity planning
        - Identifying memory leaks
        
        Returns:
            Dict containing:
            - used_memory: Bytes used by Redis
            - used_memory_human: Human-readable format
            - memory_fragmentation_ratio: >1.5 may indicate issues
        
        Libraries used:
            - Redis INFO command for memory stats
        """
        try:
            client = await self.get_client()
            if client:
                info = await client.info("memory")
                return {
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "used_memory_peak": info.get("used_memory_peak", 0),
                    "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                    "total_system_memory": info.get("total_system_memory", 0),
                    "total_system_memory_human": info.get("total_system_memory_human", "0B"),
                    "memory_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0)
                }
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
        return {}
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """Get Redis connection information"""
        try:
            client = await self.get_client()
            if client:
                info = await client.info("clients")
                return {
                    "connected_clients": info.get("connected_clients", 0),
                    "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer", 0),
                    "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer", 0),
                    "blocked_clients": info.get("blocked_clients", 0)
                }
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
        return {}
    
    async def cleanup_expired_keys(self, pattern: str, max_age_seconds: int) -> int:
        """
        Cleans up keys matching a pattern that lack proper expiration.
        
        This maintenance function helps prevent memory bloat by:
        - Finding keys without TTL (TTL = -1)
        - Setting expiration on old keys
        - Using SCAN for non-blocking operation
        
        Best practices:
        - Run during low-traffic periods
        - Test pattern on small dataset first
        - Monitor memory usage before/after
        
        Args:
            pattern: Key pattern to clean (e.g., "temp:*")
            max_age_seconds: Age threshold for cleanup
        
        Returns:
            int: Number of keys scheduled for expiration
        
        Note:
            This is a simplified implementation. Production systems
            may need custom logic based on key timestamps.
        """
        cleaned_count = 0
        try:
            client = await self.get_client()
            if not client:
                return cleaned_count
            
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                
                for key in keys:
                    ttl = await client.ttl(key)
                    if ttl == -1:  # Key has no expiration
                        # Check if key is old based on some criteria
                        # This is a simplified approach - you might need custom logic
                        await client.expire(key, max_age_seconds)
                        cleaned_count += 1
                
                if cursor == 0:
                    break
                    
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        return cleaned_count
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Performs comprehensive Redis health check with diagnostics.
        
        This method tests:
        - Basic connectivity (PING)
        - Response latency
        - Memory usage
        - Connection pool status
        - Server version and uptime
        
        Health states:
        - "healthy": All checks pass, low latency
        - "unhealthy": Connection failed or errors
        - "unavailable": No client connection
        
        Use this for:
        - Load balancer health checks
        - Monitoring dashboards
        - Automated alerts
        
        Returns:
            Dict containing:
            - status: Overall health state
            - latency_ms: PING round-trip time
            - redis_version: Server version
            - memory_usage: Memory statistics
            - error: Error message if unhealthy
        """
        try:
            client = await self.get_client()
            if not client:
                return {"status": "unavailable", "error": "No client connection"}
            
            # Test basic operations
            start_time = datetime.now()
            await client.ping()
            latency = (datetime.now() - start_time).total_seconds() * 1000
            
            # Get server info
            info = await client.info("server")
            memory_info = await self.get_memory_usage()
            connection_info = await self.get_connection_info()
            
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "redis_version": info.get("redis_version", "unknown"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "memory_usage": memory_info,
                "connection_info": connection_info,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

# Global Redis utils instance
# This singleton instance is used throughout the application for Redis operations
# It maintains a single connection pool for efficient resource usage
redis_utils = RedisUtils()