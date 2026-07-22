import re

def detect_language(text):
    if re.search(r'[\u0900-\u097F]', text):
        return "hi"
    if re.search(r'[\u0600-\u06FF]', text):
        return "ar"
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    return "en"


def get_safe_language(lang):
    supported = ["en", "es", "fr"]
    return lang if lang in supported else "en"