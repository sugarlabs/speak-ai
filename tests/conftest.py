"""
Pytest configuration for pronunciation test framework.

This module sets up fixtures and configuration for testing multilingual TTS
pronunciation accuracy.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import kokoro
sys.path.insert(0, str(Path(__file__).parent.parent))

from kokoro.pipeline import KPipeline


@pytest.fixture(scope="session")
def hindi_pipeline():
    """Create a KPipeline instance for Hindi G2P conversion (quiet mode).
    
    This fixture is session-scoped to avoid recreating the pipeline for
    each test, improving performance.
    """
    try:
        # Create a "quiet" pipeline that performs G2P without audio synthesis
        pipeline = KPipeline(lang_code='hi', model=False)
        return pipeline
    except Exception as e:
        pytest.skip(f"Hindi pipeline not available: {e}")


@pytest.fixture(scope="session")
def english_pipeline():
    """Create a KPipeline instance for English G2P conversion (quiet mode)."""
    try:
        pipeline = KPipeline(lang_code='a', model=False)  # American English
        return pipeline
    except Exception as e:
        pytest.skip(f"English pipeline not available: {e}")


@pytest.fixture(scope="session")
def available_languages():
    """Return list of languages available for testing."""
    return {
        'hi': 'Hindi',
        'a': 'American English',
        'b': 'British English',
        'e': 'Spanish',
        'f': 'French',
        'i': 'Italian',
        'p': 'Portuguese (Brazil)',
    }
