"""
ai/gemini_client.py
Fix: 429 quota exceeded raw JSON blob dumped to chat.
     - 429 now shows a clean, actionable user message instead of raw API JSON
     - Error messages trimmed to first line only (no multi-line JSON blobs)
     - Proper 2s wait before retry on rate limit
"""

import os
import json
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module="google")

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:

    def __init__(self):
        raw_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
        self.keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self.current_key_index   = 0
        self.current_model_index = 0
        self.model               = None

        # Only confirmed-working models from your CMD logs
        self.model_names = [
            'gemini-2.0-flash',   # confirmed working
            'gemini-2.5-flash',   # confirmed working
        ]

        if not self.keys:
            print("❌ AI ERROR: No API Keys found in .env!")
            return

        print(f"✅ AI Engine: Loaded {len(self.keys)} Keys.")
        self._apply_config()

    def _apply_config(self):
        if not self.keys:
            return
        key        = self.keys[self.current_key_index]
        model_name = self.model_names[self.current_model_index]
        try:
            genai.configure(api_key=key)
            self.model = genai.GenerativeModel(model_name)
            masked = key[:5] + "..." + key[-4:]
            print(f"🔑 AI Config: Key {self.current_key_index + 1} ({masked}) | Model: {model_name}")
        except Exception as e:
            print(f"❌ AI Config Error: {e}")

    def rotate_strategy(self):
        if self.current_model_index < len(self.model_names) - 1:
            self.current_model_index += 1
            print(f"🔄 Switching Model to: {self.model_names[self.current_model_index]}")
            self._apply_config()
            return True
        elif self.current_key_index < len(self.keys) - 1:
            self.current_key_index   += 1
            self.current_model_index  = 0
            print(f"🔄 Switching to API Key #{self.current_key_index + 1}")
            self._apply_config()
            return True
        return False

    def get_response(self, prompt: str) -> str:
        if not self.model:
            return "❌ AI keys missing — check GEMINI_API_KEY in your .env file."

        max_attempts = len(self.keys) * len(self.model_names)
        for _ in range(max_attempts):
            try:
                return self.model.generate_content(prompt).text

            except Exception as e:
                err = str(e)

                # ── 429 Rate limit / quota exceeded ───────────────────────────
                if "429" in err or "quota" in err.lower():
                    if self.rotate_strategy():
                        time.sleep(2)   # brief wait before retry
                        continue
                    # All keys/models exhausted — clean message only
                    return (
                        "⚠️  Gemini API quota exceeded (free tier daily limit reached).\n\n"
                        "To fix this:\n"
                        "  1. Wait until tomorrow — free tier resets daily\n"
                        "  2. Add a paid API key to GEMINI_API_KEY in your .env file\n"
                        "  3. Visit https://ai.google.dev to upgrade your plan"
                    )

                # ── 404 Model not found ───────────────────────────────────────
                if "404" in err or "not found" in err.lower():
                    if self.rotate_strategy():
                        time.sleep(1)
                        continue
                    return "❌ No working Gemini model found for your API key."

                # ── Any other error — first line only, no JSON blobs ──────────
                first_line = err.split('\n')[0].strip()[:180]
                return f"❌ AI Error: {first_line}"

        return (
            "⚠️  All Gemini API quota exceeded.\n"
            "Check your .env GEMINI_API_KEY and quota at https://ai.google.dev"
        )

    def get_json_response(self, prompt: str) -> dict | None:
        raw = self.get_response(prompt)
        if not raw or raw.startswith(("❌", "⚠️")):
            return None
        try:
            text = raw.strip()
            if text.startswith("```"):
                newline = text.find("\n")
                text = text[newline + 1:] if newline != -1 else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            try:
                start = raw.index("{")
                end   = raw.rindex("}") + 1
                return json.loads(raw[start:end])
            except (ValueError, json.JSONDecodeError):
                return None

    def analyze(self, prompt: str) -> str:
        return self.get_response(prompt)


ai_client = GeminiClient()
