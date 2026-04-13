"""
agents/base_agent.py  —  BO Commander Agent Framework  v2.0
============================================================
Base class that every specialist agent inherits.

Features:
  • Thread-safe background execution
  • Emit / streaming output callback
  • Structured result dict
  • Retry with exponential back-off
  • Self-timing and error capture
"""

import logging
import threading
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("BaseAgent")


class AgentResult:
    """Structured result from any agent action."""

    def __init__(self, success: bool, message: str, data: Any = None,
                 action: str = "", duration_ms: int = 0):
        self.success     = success
        self.message     = message
        self.data        = data or {}
        self.action      = action
        self.duration_ms = duration_ms
        self.timestamp   = datetime.now().isoformat()
        self.errors: List[str] = []

    def add_error(self, e: str):
        self.errors.append(e)
        return self

    def to_dict(self) -> dict:
        return {
            "success":     self.success,
            "message":     self.message,
            "data":        self.data,
            "action":      self.action,
            "duration_ms": self.duration_ms,
            "timestamp":   self.timestamp,
            "errors":      self.errors,
        }

    def __bool__(self):
        return self.success

    def __str__(self):
        icon = "✅" if self.success else "❌"
        parts = [f"{icon} [{self.action}] {self.message}"]
        if self.errors:
            parts += [f"  ⚠ {e}" for e in self.errors]
        return "\n".join(parts)


class BaseAgent(ABC):
    """
    Abstract base for all BO Commander agents.

    Each agent:
      1. Has a unique name and description
      2. Exposes can_handle(intent) to check if it owns an intent
      3. Implements execute(intent, emit) to run the action
      4. Runs on a background thread via run_async()
    """

    name: str = "BaseAgent"
    description: str = ""

    def __init__(self, emit_callback: Callable[[str], None] = None):
        self._emit  = emit_callback or (lambda s: None)
        self._lock  = threading.Lock()
        self._running = False
        self._last_result: Optional[AgentResult] = None
        self._history: List[Dict] = []   # last 100 results kept in memory

    # ── Abstract interface ────────────────────────────────────────────────────
    @abstractmethod
    def can_handle(self, intent: dict) -> bool:
        """Return True if this agent can handle the given intent."""
        ...

    @abstractmethod
    def execute(self, intent: dict, emit: Callable[[str], None]) -> AgentResult:
        """Execute the intent. emit() streams lines to the UI."""
        ...

    # ── Emit helpers ──────────────────────────────────────────────────────────
    def emit(self, msg: str):
        """Send a line of output to the UI."""
        try:
            self._emit(msg)
        except Exception:
            pass

    def emit_section(self, title: str):
        self.emit(f"\n{'─'*50}\n  {title}\n{'─'*50}")

    def emit_ok(self, msg: str):
        self.emit(f"✅  {msg}")

    def emit_err(self, msg: str):
        self.emit(f"❌  {msg}")

    def emit_warn(self, msg: str):
        self.emit(f"⚠   {msg}")

    def emit_info(self, msg: str):
        self.emit(f"ℹ   {msg}")

    # ── Async execution ───────────────────────────────────────────────────────
    def run_async(self, intent: dict, emit: Callable[[str], None],
                  done_callback: Callable[["AgentResult"], None] = None):
        """Run execute() in a daemon thread. Calls done_callback when finished."""
        def _run():
            start = time.time()
            result = AgentResult(False, "Not started", action=intent.get("action",""))
            try:
                result = self.execute(intent, emit)
            except Exception as e:
                tb = traceback.format_exc()
                result = AgentResult(False, f"Unhandled error: {e}",
                                     action=intent.get("action",""))
                result.add_error(tb)
                emit(f"❌  {self.name} crashed: {e}")
                logger.error(f"{self.name} exception:\n{tb}")
            finally:
                result.duration_ms = int((time.time() - start) * 1000)
                self._last_result = result
                self._history.append(result.to_dict())
                if len(self._history) > 100:
                    self._history.pop(0)
                self._running = False
                if done_callback:
                    try:
                        done_callback(result)
                    except Exception:
                        pass

        self._running = True
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    # ── Retry helper ──────────────────────────────────────────────────────────
    @staticmethod
    def retry(fn: Callable, attempts: int = 3, delay: float = 1.0,
              backoff: float = 2.0) -> Any:
        """Call fn() up to `attempts` times with exponential back-off."""
        last_exc = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if i < attempts - 1:
                    time.sleep(delay * (backoff ** i))
        raise last_exc
