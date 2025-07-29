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
    """
    A service class for handling multilingual text translations using Claude AI.
    
    This service provides:
    - AI-powered translation via Anthropic's Claude API
    - Redis-based caching for performance optimization
    - Local in-memory caching as fallback
    - Rate limiting to prevent API abuse
    - Language detection capabilities
    - Translation statistics tracking
    
    Libraries used:
        - anthropic: For Claude AI API access
        - redis.asyncio: For distributed caching and rate limiting
        - hashlib: For generating cache keys
        - asyncio: For asynchronous operations and timeouts
    """
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.cache: Dict[Tuple[str, str], str] = {}
        self.timeout = 5.0  # Increased from 1.5 to handle longer translations
        self.redis_client = None
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.cache_ttl = 86400  # 24 hours
        self.rate_limit_window = 60  # 1 minute
        self.rate_limit_max = 10  # 10 requests per minute
        
    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """
        Creates and returns a Redis client connection.
        
        This method creates a new Redis connection for each operation to avoid
        connection pooling issues and recursion problems. It includes:
        - Automatic connection retry on timeout
        - Health check intervals for connection monitoring
        - Graceful fallback if Redis is unavailable
        
        Returns:
            Optional[redis.Redis]: Redis client if connection successful, None otherwise
        
        Libraries used:
            - redis.asyncio: For asynchronous Redis operations
            - logging: For connection status tracking
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
            # Test connection
            await client.ping()
            return client
        except Exception as e:
            logger.warning(f"🔴 REDIS ❌ Connection failed: {e}")
            logger.warning("🔴 REDIS 💔 Falling back to local cache only")
            return None
    
    async def _redis_get(self, key: str) -> Optional[str]:
        """
        Safely retrieves a value from Redis with comprehensive error handling.
        
        This method:
        - Creates a new Redis connection for the operation
        - Logs cache hits/misses with emoji indicators for visibility
        - Handles connection failures gracefully
        - Always closes the connection to prevent leaks
        
        Args:
            key: The Redis key to retrieve
        
        Returns:
            Optional[str]: The cached value if found, None otherwise
        
        Emoji indicators:
            🔴 REDIS 🎯: Cache HIT
            🔴 REDIS 💨: Cache MISS
            🔴 REDIS ⚠️: Error occurred
        """
        client = None
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
        finally:
            if client:
                await client.close()
        return None
    
    async def _redis_set(self, key: str, value: str, ttl: int = None) -> bool:
        """
        Safely stores a value in Redis with optional TTL (Time To Live).
        
        This method:
        - Creates a new Redis connection for the operation
        - Supports both permanent and time-limited storage
        - Logs storage operations with emoji indicators
        - Handles connection failures gracefully
        
        Args:
            key: The Redis key to store under
            value: The value to store
            ttl: Optional time-to-live in seconds
        
        Returns:
            bool: True if storage successful, False otherwise
        
        Emoji indicators:
            🔴 REDIS 💾: Data successfully stored
            🔴 REDIS ⚠️: Storage error occurred
        """
        client = None
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
        finally:
            if client:
                await client.close()
        return False
    
    async def _redis_incr(self, key: str, ttl: int = None) -> Optional[int]:
        """
        Safely increments a Redis counter, used primarily for rate limiting.
        
        This method:
        - Atomically increments a counter in Redis
        - Sets TTL on first increment for automatic expiry
        - Used to track API usage per user/minute
        - Returns the current count for rate limit checking
        
        Args:
            key: The Redis key to increment
            ttl: Optional TTL to set on first increment
        
        Returns:
            Optional[int]: Current counter value, None if Redis unavailable
        
        Emoji indicators:
            🔴 REDIS 📊: Counter incremented successfully
        """
        client = None
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
        finally:
            if client:
                await client.close()
        return None
    
    def _get_cache_key(self, text: str, target_language: str, source_language: str = None) -> str:
        """
        Generates a unique cache key for translation lookups.
        
        This method creates cache keys using:
        - MD5 hash of the text content for consistency
        - Target language code
        - Optional source language for context-aware caching
        
        The key format ensures that identical texts with different
        source/target language pairs are cached separately.
        
        Args:
            text: The text to be translated
            target_language: Target language code (e.g., 'es', 'fr')
            source_language: Optional source language code
        
        Returns:
            str: Redis key in format 'translate:source:target:hash'
        
        Libraries used:
            - hashlib: For MD5 hash generation
        """
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if source_language:
            return f"translate:{source_language}:{target_language}:{text_hash}"
        return f"translate:{target_language}:{text_hash}"
    
    def _get_local_cache_key(self, text: str, target_language: str) -> Tuple[str, str]:
        """Generate local cache key for backward compatibility"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return (text_hash, target_language)
    
    async def translate_text(self, text: str, target_language: str, source_language: str = None, user_id: str = None) -> str:
        """
        Main translation method with caching, rate limiting, and fallback mechanisms.
        
        This comprehensive method:
        1. Checks rate limits to prevent API abuse
        2. Looks for cached translations in Redis (distributed cache)
        3. Falls back to local in-memory cache if Redis miss
        4. Calls Claude AI API if no cache hit
        5. Stores results in both cache layers
        6. Updates usage statistics
        
        The method includes multiple fallback mechanisms to ensure reliability:
        - Returns original text on rate limit exceeded
        - Returns original text on translation timeout
        - Returns original text on any API error
        
        Args:
            text: Text to translate
            target_language: Target language code
            source_language: Optional source language for better accuracy
            user_id: Optional user ID for rate limiting
        
        Returns:
            str: Translated text or original text on failure
        
        Libraries used:
            - asyncio: For timeout management
            - Claude AI: For actual translation
            - Redis: For distributed caching
        """
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
        """
        Implements per-user rate limiting to prevent API abuse.
        
        This method uses Redis to track API calls per user within a
        sliding time window. It:
        - Allows up to 10 translations per minute per user
        - Automatically resets counters after the time window
        - Gracefully allows requests if Redis is unavailable
        
        Args:
            user_id: Unique identifier for the user
        
        Returns:
            bool: True if within limits, False if exceeded
        
        Configuration:
            - Window: 60 seconds
            - Max requests: 10 per window
        """
        key = f"rate_limit:{user_id}"
        count = await self._redis_incr(key, self.rate_limit_window)
        
        if count is None:
            return True  # Redis unavailable, allow request
        
        return count <= self.rate_limit_max
    
    async def detect_language(self, text: str) -> str:
        """
        Detects the language of input text using Claude AI.
        
        This method:
        - Caches detection results to avoid repeated API calls
        - Uses MD5 hashing for consistent cache keys
        - Returns 'en' as default for empty text
        - Caches results for 1 hour to balance freshness and performance
        
        Args:
            text: Text to analyze for language detection
        
        Returns:
            str: Two-letter ISO language code (e.g., 'en', 'es', 'fr')
        
        Libraries used:
            - Claude AI: For language detection
            - hashlib: For cache key generation
        """
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
        """
        Uses Claude AI to detect the language of text.
        
        This method:
        - Sends a focused prompt to Claude for language detection
        - Uses low temperature (0.1) for consistent results
        - Validates the response is a proper 2-letter ISO code
        - Falls back to 'en' (English) on any error
        
        The method is designed to be fast with minimal token usage
        by limiting response to 50 tokens.
        
        Args:
            text: Text to analyze
        
        Returns:
            str: Two-letter ISO language code
        
        Libraries used:
            - Anthropic Claude API: For AI-powered detection
        """
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
        """
        Retrieves comprehensive translation usage statistics from Redis.
        
        This method collects:
        - Total number of translations performed
        - Cache hit/miss ratios for performance monitoring
        - Most popular target languages (top 10)
        - Error states if Redis is unavailable
        
        The statistics help monitor:
        - Cache effectiveness (hit ratio)
        - API usage patterns
        - Language popularity trends
        
        Returns:
            Dict containing:
            - total_translations: Total API calls made
            - cache_hits: Number of cache hits
            - cache_misses: Number of cache misses
            - popular_languages: Dict of language codes to usage counts
        
        Libraries used:
            - Redis ZSET: For sorted language popularity tracking
        """
        client = None
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
        finally:
            if client:
                await client.close()
    
    async def _update_stats(self, target_language: str, cache_hit: bool = False):
        """
        Updates translation statistics in Redis for monitoring and analytics.
        
        This method tracks:
        - Language popularity using Redis sorted sets (ZSET)
        - Total translation count
        - Cache performance metrics (hits vs misses)
        
        The statistics are used for:
        - Understanding user language preferences
        - Monitoring cache effectiveness
        - Capacity planning based on usage patterns
        
        Args:
            target_language: The language that was translated to
            cache_hit: Whether this was served from cache
        
        Redis operations:
            - ZINCRBY: Increment language popularity score
            - INCR: Increment various counters
        """
        client = None
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
        finally:
            if client:
                await client.close()
    
    async def _translate_with_claude(self, text: str, target_language: str) -> str:
        """
        Performs actual translation using Claude AI with carefully crafted prompts.
        
        This method:
        - Maps language codes to full language names for clarity
        - Uses specific prompt engineering for accurate translations
        - Maintains low temperature (0.1) for consistent results
        - Preserves formatting and tone of original text
        
        The prompt is designed to:
        - Produce only the translation without explanations
        - Maintain the original style and tone
        - Handle various text formats (casual, formal, technical)
        
        Args:
            text: Source text to translate
            target_language: Two-letter language code
        
        Returns:
            str: Translated text
        
        Raises:
            Exception: On API errors (caught by caller)
        
        Libraries used:
            - Anthropic Claude 3.5 Haiku: Fast, efficient model for translations
            - Temperature 0.1: For consistent, deterministic outputs
        """
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
        logger.info(f"🤖 CLAUDE TRANSLATION REQUEST: '{text}' -> {target_lang_name} ({target_language})")
        
        prompt = f"""Translate the following text to {target_lang_name}. 
        
        Important rules:
        - Only provide the translation, no explanations
        - Preserve the original tone and style
        - Keep formatting if any
        - Always translate to {target_lang_name}, even if source language is unknown
        
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
            
            result = response.content[0].text.strip()
            logger.info(f"🤖 CLAUDE RESPONSE: '{result}'")
            return result
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

translation_service = TranslationService()

async def translate_text(text: str, target_language: str, source_language: str = None, user_id: str = None) -> str:
    """
    Module-level translation function for easy importing.
    
    This convenience function provides a simple interface to the
    TranslationService singleton instance. It's the primary entry point
    for translation requests from other modules.
    
    Args:
        text: Text to translate
        target_language: Target language code (e.g., 'es', 'fr')
        source_language: Optional source language for context
        user_id: Optional user ID for rate limiting
    
    Returns:
        str: Translated text or original on failure
    
    Example:
        from translation_service import translate_text
        spanish_text = await translate_text("Hello", "es")
    """
    return await translation_service.translate_text(text, target_language, source_language, user_id)