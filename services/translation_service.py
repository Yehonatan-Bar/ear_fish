import asyncio
import hashlib
import os
from typing import Dict, Tuple
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TranslationService:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.cache: Dict[Tuple[str, str], str] = {}
        self.timeout = 1.5
    
    def _get_cache_key(self, text: str, target_language: str) -> Tuple[str, str]:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return (text_hash, target_language)
    
    async def translate_text(self, text: str, target_language: str) -> str:
        if not text.strip():
            return text
        
        cache_key = self._get_cache_key(text, target_language)
        
        if cache_key in self.cache:
            logger.info(f"Cache hit for translation to {target_language}")
            return self.cache[cache_key]
        
        try:
            translated = await asyncio.wait_for(
                self._translate_with_claude(text, target_language),
                timeout=self.timeout
            )
            
            self.cache[cache_key] = translated
            logger.info(f"Translation cached for {target_language}")
            return translated
            
        except asyncio.TimeoutError:
            logger.warning(f"Translation timeout for {target_language}, returning original")
            return text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
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

async def translate_text(text: str, target_language: str) -> str:
    return await translation_service.translate_text(text, target_language)