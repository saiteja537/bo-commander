"""ai/ollama_client.py  — FIXED VERSION
Ensures module-level singleton  ollama_client  is always importable.
Falls back gracefully if Ollama is not installed or not running.
"""

import logging
import json
import re

logger = logging.getLogger("OllamaClient")

_DEFAULT_HOST  = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"


class OllamaClient:
    """Thin wrapper around the Ollama local REST API."""

    def __init__(self, host: str = _DEFAULT_HOST, model: str = _DEFAULT_MODEL):
        self.host        = host.rstrip("/")
        self.model       = model
        self._available  = self._check_available()

    def _check_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.urlopen(f"{self.host}/api/tags", timeout=2)
            return req.status == 200
        except Exception:
            return False

    def is_available(self) -> bool:
        return self._available

    # ── core request ─────────────────────────────────────────────────────────

    def _call(self, prompt: str, model: str = None) -> str:
        if not self._available:
            raise RuntimeError("Ollama not available")
        import urllib.request
        payload = json.dumps({
            "model":  model or self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req  = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data.get("response", "")

    # ── public helpers ────────────────────────────────────────────────────────

    def get_text_response(self, prompt: str, max_tokens: int = 1024) -> str | None:
        try:
            return self._call(prompt)
        except Exception as e:
            logger.error(f"get_text_response: {e}")
            return None

    def get_json_response(self, prompt: str, max_tokens: int = 1024) -> dict | None:
        try:
            raw     = self._call(prompt)
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m:
                    return json.loads(m.group())
            return None
        except Exception as e:
            logger.error(f"get_json_response: {e}")
            return None

    def analyze(self, prompt: str) -> str:
        return self.get_text_response(prompt) or "Ollama unavailable."

    def analyze_json(self, prompt: str) -> dict:
        return self.get_json_response(prompt) or {}


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

def _create_ollama_client() -> OllamaClient:
    try:
        from config import Config  # noqa
        host  = getattr(Config, "OLLAMA_HOST",  _DEFAULT_HOST)
        model = getattr(Config, "OLLAMA_MODEL", _DEFAULT_MODEL)
        return OllamaClient(host=host, model=model)
    except Exception:
        return OllamaClient()


ollama_client: OllamaClient = _create_ollama_client()
