import asyncio
import hashlib
import os
import json
import time
from typing import Dict, Tuple, Optional, Any
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv()

logger = logging.getLogger(__name__)

class TranslationService:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.cache: Dict[Tuple[str, str], str] = {}
        self.timeout = 1.5
        self.redis_client = None
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.cache_ttl = 86400  # 24 hours
        self.rate_limit_window = 60  # 1 minute
        self.rate_limit_max = 10  # 10 requests per minute
        
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client with connection pooling and error handling"""
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
                # Test connection
                await self.redis_client.ping()
                logger.info("🔴 REDIS ✅ Connection established successfully!")
                logger.info(f"🔴 REDIS 🔗 Connected to: {self.redis_url}")
            except Exception as e:
                logger.warning(f"🔴 REDIS ❌ Connection failed: {e}")
                logger.warning("🔴 REDIS 💔 Falling back to local cache only")
                self.redis_client = None
        return self.redis_client
    
    async def _redis_get(self, key: str) -> Optional[str]:
        """Safe Redis get with error handling"""
        try:
            client = await self._get_redis_client()
            if client:
                result = await client.get(key)
                if result:
                    logger.info(f"🔴 REDIS 🎯 Cache HIT for key: {key[:50]}...")
                else:
                    logger.info(f"🔴 REDIS 💨 Cache MISS for key: {key[:50]}...")
                return result
        except Exception as e:
            logger.warning(f"🔴 REDIS ⚠️  Get error: {e}")
        return None
    
    async def _redis_set(self, key: str, value: str, ttl: int = None) -> bool:
        """Safe Redis set with error handling"""
        try:
            client = await self._get_redis_client()
            if client:
                if ttl:
                    await client.setex(key, ttl, value)
                    logger.info(f"🔴 REDIS 💾 Cached with TTL {ttl}s: {key[:50]}... = {value[:30]}...")
                else:
                    await client.set(key, value)
                    logger.info(f"🔴 REDIS 💾 Cached permanently: {key[:50]}... = {value[:30]}...")
                return True
        except Exception as e:
            logger.warning(f"🔴 REDIS ⚠️  Set error: {e}")
        return False
    
    async def _redis_incr(self, key: str, ttl: int = None) -> Optional[int]:
        """Safe Redis increment with error handling"""
        try:
            client = await self._get_redis_client()
            if client:
                count = await client.incr(key)
                if ttl and count == 1:
                    await client.expire(key, ttl)
                logger.info(f"🔴 REDIS 📊 Rate limit counter: {key} = {count}")
                return count
        except Exception as e:
            logger.warning(f"🔴 REDIS ⚠️  Incr error: {e}")
        return None
    
    def _get_cache_key(self, text: str, target_language: str, source_language: str = None) -> str:
        """Generate cache key with context awareness"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if source_language:
            return f"translate:{source_language}:{target_language}:{text_hash}"
        return f"translate:{target_language}:{text_hash}"
    
    def _get_local_cache_key(self, text: str, target_language: str) -> Tuple[str, str]:
        """Generate local cache key for backward compatibility"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return (text_hash, target_language)
    
    async def translate_text(self, text: str, target_language: str, source_language: str = None, user_id: str = None) -> str:
        """Enhanced translation with Redis caching and rate limiting"""
        if not text.strip():
            return text
        
        # Rate limiting check
        if user_id and not await self._check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return text
        
        # Try Redis cache first
        redis_key = self._get_cache_key(text, target_language, source_language)
        cached_result = await self._redis_get(redis_key)
        
        if cached_result:
            logger.info(f"🔴 REDIS ✨ CACHE HIT! Translation '{text[:20]}...' -> {target_language}: '{cached_result[:30]}...'")
            await self._update_stats(target_language, cache_hit=True)
            return cached_result
        
        # Fall back to local cache
        local_key = self._get_local_cache_key(text, target_language)
        if local_key in self.cache:
            logger.info(f"💻 LOCAL CACHE HIT! Translation '{text[:20]}...' -> {target_language}: '{self.cache[local_key][:30]}...'")
            # Update Redis cache asynchronously
            logger.info("🔴 REDIS ⬆️  Syncing local cache to Redis...")
            await self._redis_set(redis_key, self.cache[local_key], self.cache_ttl)
            await self._update_stats(target_language, cache_hit=True)
            return self.cache[local_key]
        
        try:
            logger.info(f"🤖 CLAUDE API CALL! Translating '{text[:20]}...' to {target_language}")
            translated = await asyncio.wait_for(
                self._translate_with_claude(text, target_language),
                timeout=self.timeout
            )
            
            # Store in both caches
            logger.info(f"✅ NEW TRANSLATION! '{text[:20]}...' -> {target_language}: '{translated[:30]}...'")
            self.cache[local_key] = translated
            logger.info("🔴 REDIS 💾 Storing new translation in Redis cache...")
            await self._redis_set(redis_key, translated, self.cache_ttl)
            await self._update_stats(target_language, cache_hit=False)
            
            return translated
            
        except asyncio.TimeoutError:
            logger.warning(f"Translation timeout for {target_language}, returning original")
            return text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
    async def _check_rate_limit(self, user_id: str) -> bool:
        """Check if user is within rate limits"""
        key = f"rate_limit:{user_id}"
        count = await self._redis_incr(key, self.rate_limit_window)
        
        if count is None:
            return True  # Redis unavailable, allow request
        
        return count <= self.rate_limit_max
    
    async def detect_language(self, text: str) -> str:
        """Detect language with Redis caching"""
        if not text.strip():
            return "en"
        
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"detect:{text_hash}"
        
        # Check cache first
        cached_lang = await self._redis_get(cache_key)
        if cached_lang:
            logger.info(f"Language detection cache hit: {cached_lang}")
            return cached_lang
        
        # Simple language detection (you can replace with a proper library)
        detected_lang = await self._detect_language_with_claude(text)
        
        # Cache the result
        await self._redis_set(cache_key, detected_lang, 3600)  # 1 hour TTL
        
        return detected_lang
    
    async def _detect_language_with_claude(self, text: str) -> str:
        """Detect language using Claude API"""
        try:
            response = await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=50,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": f"Detect the language of this text and return only the 2-letter ISO code: {text}"}
                ]
            )
            
            detected = response.content[0].text.strip().lower()
            # Validate it's a 2-letter code
            if len(detected) == 2 and detected.isalpha():
                return detected
            return "en"  # Default fallback
            
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return "en"  # Default fallback
    
    async def get_translation_stats(self) -> Dict[str, Any]:
        """Get translation statistics from Redis"""
        try:
            client = await self._get_redis_client()
            if not client:
                return {"error": "Redis unavailable"}
            
            # Get popular languages
            popular_langs = await client.zrevrange("popular_languages", 0, 9, withscores=True)
            
            # Get total translations
            total_translations = await client.get("total_translations") or "0"
            
            # Get cache hit ratio
            cache_hits = await client.get("cache_hits") or "0"
            cache_misses = await client.get("cache_misses") or "0"
            
            return {
                "total_translations": int(total_translations),
                "cache_hits": int(cache_hits),
                "cache_misses": int(cache_misses),
                "popular_languages": dict(popular_langs) if popular_langs else {}
            }
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {"error": str(e)}
    
    async def _update_stats(self, target_language: str, cache_hit: bool = False):
        """Update translation statistics"""
        try:
            client = await self._get_redis_client()
            if client:
                await client.zincrby("popular_languages", 1, target_language)
                await client.incr("total_translations")
                if cache_hit:
                    await client.incr("cache_hits")
                else:
                    await client.incr("cache_misses")
        except Exception as e:
            logger.warning(f"Stats update error: {e}")
    
    async def _translate_with_claude(self, text: str, target_language: str) -> str:
        language_codes = {
            "en": "English",
            "es": "Spanish", 
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
            "he": "Hebrew",
            "th": "Thai",
            "vi": "Vietnamese",
            "tr": "Turkish",
            "pl": "Polish",
            "nl": "Dutch",
            "sv": "Swedish",
            "da": "Danish",
            "no": "Norwegian",
            "fi": "Finnish"
        }
        
        target_lang_name = language_codes.get(target_language, target_language)
        
        prompt = f"""Translate the following text to {target_lang_name}. 
        
        Important rules:
        - Only provide the translation, no explanations
        - Preserve the original tone and style
        - Keep formatting if any
        - If the text is already in {target_lang_name}, return it unchanged
        
        Text to translate: {text}"""
        
        try:
            response = await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

translation_service = TranslationService()

async def translate_text(text: str, target_language: str, source_language: str = None, user_id: str = None) -> str:
    return await translation_service.translate_text(text, target_language, source_language, user_id)