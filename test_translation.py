#!/usr/bin/env python3
import asyncio
import json
from backend.translation_service import translation_service

async def test_translation():
    # Test cases
    test_cases = [
        {
            "text": "How are you?",
            "source": "en",
            "target": "he",
            "expected": "מה שלומך?"
        },
        {
            "text": "האמת שדרסה אותי חללית",
            "source": "he", 
            "target": "en",
            "expected": "The truth is a spaceship ran me over"
        },
        {
            "text": "שלום",
            "source": "he",
            "target": "en", 
            "expected": "Hello"
        }
    ]
    
    print("Testing translation service...")
    print("-" * 50)
    
    for test in test_cases:
        print(f"\nTest: {test['text']}")
        print(f"From: {test['source']} -> To: {test['target']}")
        
        result = await translation_service.translate_text(
            text=test['text'],
            target_language=test['target'],
            source_language=test['source'],
            user_id="test_user"
        )
        
        print(f"Result: {result}")
        print(f"Expected similar to: {test['expected']}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_translation())