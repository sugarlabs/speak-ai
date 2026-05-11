import json
import hashlib
from pathlib import Path
from collections import OrderedDict
from typing import Optional


class ResponseCache:
    def __init__(self, max_cache_size: int = 100, cache_file: Optional[str] = None):
        # initialize the response catcha
    
        self.max_cache_size = max_cache_size
        self.cache_file = cache_file
        self.cache = OrderedDict()  # Ordered dict for LRU tracking
        self.hits = 0
        self.misses = 0
        
        # Load existing cache from file if provided
        if self.cache_file:
            self._load_from_file()
    
    def _normalize_question(self, question: str) -> str:
        return " ".join(question.strip().lower().split())
    
    def _get_cache_key(self, question: str) -> str:
        normalized = self._normalize_question(question)
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def get(self, question: str) -> Optional[str]:
        cache_key = self._get_cache_key(question)
        
        if cache_key in self.cache:
            # Move to end (mark as most recently used)
            self.cache.move_to_end(cache_key)
            self.hits += 1
            return self.cache[cache_key]
        
        self.misses += 1
        return None
    
    def set(self, question: str, response: str) -> None:
        cache_key = self._get_cache_key(question)
        
        # If key exists, update and move to end
        if cache_key in self.cache:
            self.cache.move_to_end(cache_key)
            self.cache[cache_key] = response
            return
        
        # Add new entry
        self.cache[cache_key] = response
        
        # Evict oldest entry if cache is full
        if len(self.cache) > self.max_cache_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        # Persist to file if configured
        if self.cache_file:
            self._save_to_file()
    
    def clear(self) -> None:
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        
        # Clear cache file if it exists
        if self.cache_file and Path(self.cache_file).exists():
            Path(self.cache_file).unlink()
    
    def _save_to_file(self) -> None:
        try:
            cache_data = {
                "metadata": {
                    "hits": self.hits,
                    "misses": self.misses,
                    "size": len(self.cache)
                },
                "cache": dict(self.cache)
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save cache to {self.cache_file}: {e}")
    
    def _load_from_file(self) -> None:
        try:
            cache_path = Path(self.cache_file)
            if cache_path.exists():
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                # Restore cache
                if "cache" in cache_data:
                    self.cache = OrderedDict(cache_data["cache"])
                
                # Restore statistics
                if "metadata" in cache_data:
                    self.hits = cache_data["metadata"].get("hits", 0)
                    self.misses = cache_data["metadata"].get("misses", 0)
        except Exception as e:
            print(f"Warning: Failed to load cache from {self.cache_file}: {e}")
    
    def get_stats(self) -> dict:
        """Return cache statistics."""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_size": len(self.cache),
            "max_cache_size": self.max_cache_size,
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2)
        }


def create_cache(max_size: int = 100, cache_file: Optional[str] = None) -> ResponseCache:
    # function to create a response catcha
    return ResponseCache(max_cache_size=max_size, cache_file=cache_file)
