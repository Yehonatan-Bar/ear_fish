import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisUtils:
    """Utility class for common Redis operations across the application"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client = None
        self._connection_pool = None
        
    async def get_client(self) -> Optional[redis.Redis]:
        """Get Redis client with connection pooling"""
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
        """Safely get value from Redis with error handling"""
        try:
            client = await self.get_client()
            if client:
                result = await client.get(key)
                return result if result is not None else default
        except Exception as e:
            logger.warning(f"Redis get error for key {key}: {e}")
        return default
    
    async def safe_set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Safely set value in Redis with error handling"""
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
        """Safely increment counter in Redis"""
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
        """Safely get hash field from Redis"""
        try:
            client = await self.get_client()
            if client:
                result = await client.hget(key, field)
                return result if result is not None else default
        except Exception as e:
            logger.warning(f"Redis hget error for key {key}, field {field}: {e}")
        return default
    
    async def safe_hset(self, key: str, field: str = None, value: Any = None, mapping: Dict = None) -> bool:
        """Safely set hash field in Redis"""
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
        """Safely push values to list in Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.lpush(key, *values)
        except Exception as e:
            logger.warning(f"Redis lpush error for key {key}: {e}")
        return None
    
    async def safe_lrange(self, key: str, start: int, end: int) -> List[Any]:
        """Safely get range of list values from Redis"""
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
        """Safely add values to set in Redis"""
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
        """Safely increment sorted set score in Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.zincrby(key, amount, value)
        except Exception as e:
            logger.warning(f"Redis zincrby error for key {key}: {e}")
        return None
    
    async def safe_zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> List[Any]:
        """Safely get sorted set range in reverse order from Redis"""
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
        """Safely get keys matching pattern from Redis"""
        try:
            client = await self.get_client()
            if client:
                return await client.keys(pattern)
        except Exception as e:
            logger.warning(f"Redis keys error for pattern {pattern}: {e}")
        return []
    
    async def safe_scan(self, cursor: int = 0, match: str = None, count: int = None) -> tuple:
        """Safely scan Redis keys"""
        try:
            client = await self.get_client()
            if client:
                return await client.scan(cursor=cursor, match=match, count=count)
        except Exception as e:
            logger.warning(f"Redis scan error: {e}")
        return (0, [])
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """Get Redis memory usage statistics"""
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
        """Clean up keys older than specified age"""
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
        """Comprehensive Redis health check"""
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
redis_utils = RedisUtils()