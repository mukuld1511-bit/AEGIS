"""AEGIS Raspberry Pi Audio & Voice Pipeline.
Runs locally on Raspberry Pi 8GB: Wake-Word detection ('AEGIS'), multilingual STT (Hindi/English), and offline TTS.
"""
import asyncio
import os
import subprocess
import shutil

class PiVoiceService:
    def __init__(self, wake_word: str = "aegis", lang: str = "hi-en"):
        self.wake_word = wake_word.lower()
        self.lang = lang
        self.has_piper = shutil.which("piper") is not None
        self.has_espeak = shutil.which("espeak-ng") is not None

    async def speak_response(self, text: str):
        """Speaks the response out of the Raspberry Pi 3.5mm jack / USB speaker."""
        print(f"[Pi Speaker]: {text}")

        # If Piper TTS is installed on Pi OS (High-quality offline neural voice)
        if self.has_piper:
            try:
                cmd = f"echo '{text}' | piper --model en_US-lessac-medium --output_raw | aplay -r 22050 -f S16_LE -t raw -"
                subprocess.Popen(cmd, shell=True)
                return
            except Exception:
                pass

        # Fallback to espeak-ng (lightweight pre-installed Linux TTS)
        if self.has_espeak:
            try:
                subprocess.Popen(["espeak-ng", "-s", "160", "-v", "en-us", text])
                return
            except Exception:
                pass

    def parse_wake_word(self, transcribed_text: str) -> bool:
        """Checks if the wake word 'AEGIS' was spoken."""
        return self.wake_word in transcribed_text.lower()
