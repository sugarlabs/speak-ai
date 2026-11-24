
import os
from sugar3.activity.activity import get_activity_root

def get_sugar_cache_dir():
    """Get the Sugar activity root cache directory for HuggingFace downloads."""
    cache_dir = os.path.join(get_activity_root(), 'data', 'kokoro_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir
