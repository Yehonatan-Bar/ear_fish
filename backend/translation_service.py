# Translation service using Claude API for multilingual chat
import asyncio
import hashlib
import os
from typing import Dict, Tuple
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Service for handling text translation using Claude API
class TranslationService:
    def __init__(self):
        # Initialize Claude API client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        logger.info(f"Initializing TranslationService with API key: {api_key[:10]}..." if api_key else "No API key found!")
        try:
            self.client = AsyncAnthropic(api_key=api_key)
            logger.info("AsyncAnthropic client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AsyncAnthropic client: {e}")
            raise
        # Cache for storing translations to avoid repeated API calls
        self.cache: Dict[Tuple[str, str], str] = {}
        # Timeout for API calls to prevent hanging
        self.timeout = 1.5
    
    # Generate cache key for storing translations
    def _get_cache_key(self, text: str, target_language: str) -> Tuple[str, str]:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return (text_hash, target_language)
    
    # Main translation method with caching and error handling
    async def translate_text(self, text: str, target_language: str) -> str:
        logger.info(f"Starting translation: '{text}' to '{target_language}'")
        
        # Skip empty text
        if not text.strip():
            logger.warning("Empty text provided for translation")
            return text
        
        # Check cache first
        cache_key = self._get_cache_key(text, target_language)
        
        if cache_key in self.cache:
            logger.info(f"Cache hit for translation to {target_language}")
            return self.cache[cache_key]
        
        # Make API call with timeout
        logger.info(f"Cache miss, calling Claude API for {target_language}")
        try:
            translated = await asyncio.wait_for(
                self._translate_with_claude(text, target_language),
                timeout=self.timeout
            )
            
            # Cache the result
            self.cache[cache_key] = translated
            logger.info(f"Translation cached for {target_language}: '{translated}'")
            return translated
            
        except asyncio.TimeoutError:
            logger.warning(f"Translation timeout for {target_language}, returning original")
            return text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
    # Make actual API call to Claude for translation
    async def _translate_with_claude(self, text: str, target_language: str) -> str:
        # Language code to name mapping
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
        
        # Get full language name from code
        target_lang_name = language_codes.get(target_language, target_language)
        
        # Construct translation prompt
        prompt = f"""Translate the following text to {target_lang_name}. 
        
        Important rules:
        - Only provide the translation, no explanations
        - Preserve the original tone and style
        - Keep formatting if any
        - If the text is already in {target_lang_name}, return it unchanged
        
        Text to translate: {text}"""
        
        # Call Claude API with translation prompt
        try:
            response = await self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0.1,  # Low temperature for consistent translations
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise

# Global translation service instance
translation_service = TranslationService()

# Convenience function for external use
async def translate_text(text: str, target_language: str) -> str:
    return await translation_service.translate_text(text, target_language)