#!/usr/bin/env python3
"""
Test script for the translation service functionality.

This script provides a simple way to test the translation capabilities
of the system, including both English to Hebrew and Hebrew to English
translations. It's useful for verifying that the translation service
is working correctly with the Claude AI backend.

Libraries used:
    - asyncio: For asynchronous execution of translation tests
    - json: Imported but not used (can be removed)
    - translation_service: The main translation module being tested
"""
import asyncio
import json
from backend.translation_service import translation_service

async def test_translation():
    """
    Tests the translation service with predefined test cases.
    
    This function runs a series of translation tests to verify:
    - English to Hebrew translation
    - Hebrew to English translation
    - Common phrases and edge cases
    - Cache functionality (subsequent runs will be faster)
    
    The test cases include:
    1. Simple English phrase to Hebrew
    2. Complex Hebrew sentence to English (spaceship example)
    3. Basic Hebrew greeting to English
    
    Each test displays:
    - Original text
    - Source and target languages
    - Translation result
    - Expected result for manual comparison
    
    Note: Translation results may vary slightly from expected values
    as AI models can produce different valid translations.
    """
    # Test cases with expected translations for verification
    # These cases test bidirectional translation between English and Hebrew
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
    
    # Display test header for clarity
    print("Testing translation service...")
    print("-" * 50)
    
    # Iterate through each test case and perform translation
    for test in test_cases:
        print(f"\nTest: {test['text']}")
        print(f"From: {test['source']} -> To: {test['target']}")
        
        # Call the translation service with test parameters
        # user_id is provided for rate limiting tracking
        result = await translation_service.translate_text(
            text=test['text'],
            target_language=test['target'],
            source_language=test['source'],
            user_id="test_user"
        )
        
        # Display results for manual verification
        # Note: AI translations may not exactly match expected values
        print(f"Result: {result}")
        print(f"Expected similar to: {test['expected']}")
        print("-" * 30)

if __name__ == "__main__":
    # Entry point for the test script
    # Uses asyncio.run() to execute the async test function
    # This allows the script to be run directly from command line:
    # python test_translation.py
    asyncio.run(test_translation())