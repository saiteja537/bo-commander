# ai/ai_factory.py
import os
from ai.gemini_client import ai_client as gemini

class AIProvider:
    @staticmethod
    def get_provider():
        # Read user preference from config or env
        provider = os.getenv("AI_PROVIDER", "GEMINI").upper()
        
        if provider == "GEMINI":
            return gemini
        elif provider == "OPENAI":
            # import openai_client (to be created)
            # return openai_client
            pass
        elif provider == "OLLAMA":
            # import ollama_client (to be created)
            # return ollama_client
            pass
        
        return gemini # Default