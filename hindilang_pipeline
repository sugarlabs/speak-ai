import epitran
import subprocess
from functools import lru_cache

def clean_hindi_phonemes(phonemes: str) -> str:
    if phonemes.endswith("ə"):
        phonemes = phonemes[:-1]
    phonemes = phonemes.replace("ə ", " ")
    return phonemes

class HindiG2P:
    def __init__(self):
        self.epi = epitran.Epitran('hin-Deva')

    @lru_cache(maxsize=1000)
    def convert(self, text):
        return self.epi.transliterate(text)


class HindiTTS:
    def __init__(self):
        self.g2p = HindiG2P()

    def speak(self, text):
        phonemes = self.g2p.convert(text)
        phonemes = clean_hindi_phonemes(phonemes)
        print("Text:", text)
        print("Improved Phonemes:", phonemes)

        subprocess.run(["espeak-ng", "-v", "hi", text])
    


if __name__ == "__main__":
    tts = HindiTTS()
    text = input("Enter Hindi text: ")
    tts.speak(text)
