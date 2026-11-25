from gtts import gTTS

text = "नमस्ते, मैं स्पीक एआई प्रोजेक्ट पर काम कर रही हूँ"

tts = gTTS(text=text, lang='hi')

tts.save("hindi_output.mp3")

print("Audio generated!")