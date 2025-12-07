#!/usr/bin/env python3
"""
Test script to verify the profanity_check.py fix.
This tests the examples from issue #3.
"""

import sys
import os

# Add GenAI directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'GenAI'))

from profainity_check import is_profane

def test_profanity_check():
    """Test cases to verify profanity detection works correctly"""
    
    print("Testing profanity_check.py fix...")
    print("=" * 50)
    
    # Test cases from the issue
    test_cases = [
        # (text, expected_result, description)
        ("hello yobbo", True, "should detect 'yobbo' as profane"),
        ("hello world", False, "should NOT detect profanity in clean text"),
        ("fuck", True, "should detect profanity"),
        ("this is a test", False, "should NOT detect profanity in clean text"),
        ("ass", True, "should detect profanity"),
        ("hello", False, "clean word should return False"),
        ("damn it", True, "should detect profanity"),
        ("good morning", False, "clean phrase should return False"),
    ]
    
    all_passed = True
    
    for text, expected, description in test_cases:
        result = is_profane(text)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        
        if result != expected:
            all_passed = False
            
        print(f"{status}: is_profane('{text}') = {result} (expected {expected})")
        print(f"        {description}")
        print()
    
    print("=" * 50)
    if all_passed:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = test_profanity_check()
    sys.exit(exit_code)
