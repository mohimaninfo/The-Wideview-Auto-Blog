"""
quota_manager.py — Gemini API quota tracker with exponential backoff + jitter.

Tracks:
- Daily request count (resets at midnight UTC)
- Daily token count
- Per-minute request rate
- Active model (primary vs fallback)

Persists state to quota_state.json between GitHub Actions steps within a run.
State is never committed to git (gitignored).
"""

import json
import logging
import random
import time
from datetime import datetime, timezone, date
from pathlib import Path
from threading import Lock
from typing import Optional

from config.settings import GeminiConfig, LoggingConfig

logger = logging.getLogger(__name__)

_lock = Lock()

QUOTA_STATE_FILE = str(LoggingConfig.QUOTA_STATE)

DAILY_LIMITS = {
    GeminiConfig.PRIMARY_MODEL: GeminiConfig.DAILY_TOKEN_LIMIT,
    "gemini-3.1-flash-lite": GeminiConfig.DAILY_TOKEN_LIMIT,
    GeminiConfig.FALLBACK_MODEL: GeminiConfig.DAILY_TOKEN_LIMIT,
    "gemini-1.5-flash": GeminiConfig.DAILY_TOKEN_LIMIT,
}

class QuotaExhaustedError(Exception):
    """Raised when all quota — primary and fallback — is exhausted."""
    pass


class QuotaManager:
    """
    Manages Gemini API quota across daily limits and per-minute rate limits.

    Thread-safe for single-process use (GitHub Actions is single-threaded).
    State persists to disk between agent calls within the same pipeline run.
    """

    def __init__(self):
        self.state_path = Path(QUOTA_STATE_FILE)
        self._state = self._load_state()
        self._legacy_state = {
            GeminiConfig.PRIMARY_MODEL: {"tokens": int(self._state.get("primary_tokens", 0))},
            GeminiConfig.FALLBACK_MODEL: {"tokens": int(self._state.get("fallback_tokens", 0))},
            "_date": self._state.get("date", str(date.today())),
        }

    @property
    def state(self) -> dict:
        """Legacy nested dict used by older tests and scripts."""
        return self._legacy_state

    def _sync_legacy_to_internal(self) -> None:
        self._state["primary_tokens"] = int(self._legacy_state[GeminiConfig.PRIMARY_MODEL]["tokens"])
        self._state["fallback_tokens"] = int(self._legacy_state[GeminiConfig.FALLBACK_MODEL]["tokens"])
        self._state["date"] = str(self._legacy_state.get("_date", self._state.get("date", str(date.today()))))

    def _sync_internal_to_legacy(self) -> None:
        self._legacy_state[GeminiConfig.PRIMARY_MODEL]["tokens"] = int(self._state.get("primary_tokens", 0))
        self._legacy_state[GeminiConfig.FALLBACK_MODEL]["tokens"] = int(self._state.get("fallback_tokens", 0))
        self._legacy_state["_date"] = self._state.get("date", str(date.today()))

    def get_usage(self, model: str) -> int:
        if model in (GeminiConfig.PRIMARY_MODEL, "gemini-3.1-flash-lite"):
            return int(self._legacy_state[GeminiConfig.PRIMARY_MODEL]["tokens"])
        return int(self._legacy_state[GeminiConfig.FALLBACK_MODEL]["tokens"])

    def increment(self, model: str, tokens: int = 0) -> None:
        with _lock:
            if model in (GeminiConfig.PRIMARY_MODEL, "gemini-3.1-flash-lite"):
                self._state["primary_tokens"] = int(self._state.get("primary_tokens", 0)) + int(tokens)
                self._state["primary_requests"] = int(self._state.get("primary_requests", 0)) + 1
            else:
                self._state["fallback_tokens"] = int(self._state.get("fallback_tokens", 0)) + int(tokens)
                self._state["fallback_requests"] = int(self._state.get("fallback_requests", 0)) + 1
            self._sync_internal_to_legacy()
            self._save_state()

    def is_quota_exceeded(self, model: str) -> bool:
        limit = DAILY_LIMITS.get(model, GeminiConfig.DAILY_TOKEN_LIMIT)
        return self.get_usage(model) >= limit

    def get_active_model(self) -> str:
        if self.get_usage(GeminiConfig.PRIMARY_MODEL) >= GeminiConfig.DAILY_TOKEN_LIMIT:
            return GeminiConfig.FALLBACK_MODEL
        return GeminiConfig.PRIMARY_MODEL

    def save(self) -> None:
        with _lock:
            self._sync_legacy_to_internal()
            self._save_state()

    # ── State persistence ─────────────────────────────────────────────────────

    def _default_state(self) -> dict:
        return {
            "date": str(date.today()),
            "primary_requests": 0,
            "primary_tokens": 0,
            "fallback_requests": 0,
            "fallback_tokens": 0,
            "active_model": GeminiConfig.PRIMARY_MODEL,
            "minute_window_start": time.time(),
            "minute_requests": 0,
            "last_request_time": 0.0,
            "consecutive_errors": 0,
        }

    def _load_state(self) -> dict:
        """Load quota state from disk. Resets if date has changed."""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                # Reset if it's a new day
                if state.get("date") != str(date.today()):
                    logger.info("New day detected — resetting quota state.")
                    return self._default_state()
                return state
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Corrupt quota state file, resetting: {e}")

        return self._default_state()

    def _save_state(self) -> None:
        """Persist quota state to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(self._state, f, indent=2)

    # ── Model selection ───────────────────────────────────────────────────────

    @property
    def active_model(self) -> str:
        return self._state["active_model"]

    def _switch_to_fallback(self) -> None:
        """Switch from primary to fallback model."""
        if self._state["active_model"] != GeminiConfig.FALLBACK_MODEL:
            logger.warning(
                f"Switching from {GeminiConfig.PRIMARY_MODEL} to fallback "
                f"{GeminiConfig.FALLBACK_MODEL} — quota exhausted."
            )
            self._state["active_model"] = GeminiConfig.FALLBACK_MODEL
            self._save_state()

    def _check_daily_quota(self) -> None:
        """
        Check if daily quota is available. Switches to fallback if primary
        is exhausted. Raises QuotaExhaustedError if both are exhausted.
        """
        model = self._state["active_model"]

        if model == GeminiConfig.PRIMARY_MODEL:
            requests_used = self._state["primary_requests"]
            tokens_used = self._state["primary_tokens"]
        else:
            requests_used = self._state["fallback_requests"]
            tokens_used = self._state["fallback_tokens"]

        req_limit = GeminiConfig.DAILY_REQUEST_LIMIT
        token_limit = GeminiConfig.DAILY_TOKEN_LIMIT

        if requests_used >= req_limit:
            if model == GeminiConfig.PRIMARY_MODEL:
                self._switch_to_fallback()
                # Check fallback quota
                if self._state["fallback_requests"] >= req_limit:
                    raise QuotaExhaustedError(
                        "Both primary and fallback Gemini models have exhausted daily quota."
                    )
            else:
                raise QuotaExhaustedError(
                    f"Fallback model {GeminiConfig.FALLBACK_MODEL} daily quota exhausted."
                )

        if tokens_used >= token_limit:
            if model == GeminiConfig.PRIMARY_MODEL:
                self._switch_to_fallback()
            else:
                raise QuotaExhaustedError("Daily token limit exhausted on all models.")

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _enforce_rate_limit(self) -> None:
        """
        Enforce per-minute request rate limit.
        Sleeps if the current minute window has reached the RPM cap.
        """
        now = time.time()
        window_start = self._state["minute_window_start"]
        elapsed = now - window_start

        # Reset window if more than 60 seconds have passed
        if elapsed >= 60.0:
            self._state["minute_window_start"] = now
            self._state["minute_requests"] = 0
            return

        # Check if we're at the RPM limit
        if self._state["minute_requests"] >= GeminiConfig.REQUESTS_PER_MINUTE:
            wait_time = 60.0 - elapsed + 1.0  # +1s safety buffer
            logger.info(
                f"Rate limit: {self._state['minute_requests']} RPM reached. "
                f"Waiting {wait_time:.1f}s..."
            )
            time.sleep(wait_time)
            self._state["minute_window_start"] = time.time()
            self._state["minute_requests"] = 0

    # ── Backoff logic ─────────────────────────────────────────────────────────

    def compute_backoff(self, attempt: int) -> float:
        """
        Compute exponential backoff with jitter.

        Formula: min(base * 2^attempt * (1 ± jitter), max_backoff)
        Jitter prevents thundering herd if multiple agents retry simultaneously.
        """
        base = GeminiConfig.BASE_BACKOFF_SECONDS
        max_backoff = GeminiConfig.MAX_BACKOFF_SECONDS
        jitter = GeminiConfig.JITTER_FACTOR

        exponential = base * (2 ** attempt)
        jitter_amount = exponential * jitter * (2 * random.random() - 1)  # ± jitter%
        backoff = min(exponential + jitter_amount, max_backoff)

        return max(backoff, 0.5)  # Minimum 0.5s backoff

    # ── Request registration ───────────────────────────────────────────────────

    def before_request(self) -> str:
        """
        Call before making a Gemini API request.
        - Checks daily quota
        - Enforces rate limit
        - Returns the model to use

        Raises QuotaExhaustedError if no quota remains.
        """
        with _lock:
            self._check_daily_quota()
            self._enforce_rate_limit()
            return self.active_model

    def after_request(self, tokens_used: int = 0, success: bool = True) -> None:
        """
        Call after a Gemini API request completes.
        Updates request and token counters.
        """
        with _lock:
            model = self._state["active_model"]

            if model == GeminiConfig.PRIMARY_MODEL:
                self._state["primary_requests"] += 1
                self._state["primary_tokens"] += tokens_used
            else:
                self._state["fallback_requests"] += 1
                self._state["fallback_tokens"] += tokens_used

            self._state["minute_requests"] += 1
            self._state["last_request_time"] = time.time()

            if success:
                self._state["consecutive_errors"] = 0
            else:
                self._state["consecutive_errors"] += 1

            self._save_state()

    def get_status(self) -> dict:
        """Return a human-readable quota status summary."""
        s = self._state
        return {
            "date": s["date"],
            "active_model": s["active_model"],
            "primary_requests_used": s["primary_requests"],
            "primary_requests_limit": GeminiConfig.DAILY_REQUEST_LIMIT,
            "primary_tokens_used": s["primary_tokens"],
            "primary_tokens_limit": GeminiConfig.DAILY_TOKEN_LIMIT,
            "fallback_requests_used": s["fallback_requests"],
            "minute_requests": s["minute_requests"],
            "consecutive_errors": s["consecutive_errors"],
        }

    def log_daily_usage(self) -> None:
        """Append today's quota usage to the quota log file."""
        log_path = LoggingConfig.QUOTA_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **self.get_status()
        }

        # Load existing log
        log_data = []
        if log_path.exists():
            try:
                with open(log_path, "r") as f:
                    log_data = json.load(f)
            except json.JSONDecodeError:
                log_data = []

        log_data.append(entry)

        # Keep last 90 days of entries
        log_data = log_data[-90:]

        with open(log_path, "w") as f:
            json.dump(log_data, f, indent=2)


# ── Retry decorator ───────────────────────────────────────────────────────────

def with_quota_retry(quota_manager: QuotaManager):
    """
    Decorator factory that wraps a Gemini API call with retry + backoff logic.

    Usage:
        @with_quota_retry(quota_manager)
        def my_api_call():
            ...
    """
    import functools

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(GeminiConfig.MAX_RETRIES):
                try:
                    model = quota_manager.before_request()
                    result = func(*args, model=model, **kwargs)
                    quota_manager.after_request(success=True)
                    return result

                except QuotaExhaustedError:
                    raise  # Don't retry on quota exhaustion

                except Exception as e:
                    last_exception = e
                    quota_manager.after_request(success=False)

                    backoff = quota_manager.compute_backoff(attempt)
                    logger.warning(
                        f"Gemini API error (attempt {attempt+1}/{GeminiConfig.MAX_RETRIES}): "
                        f"{type(e).__name__}: {str(e)[:100]}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)

            raise RuntimeError(
                f"Gemini API call failed after {GeminiConfig.MAX_RETRIES} attempts. "
                f"Last error: {last_exception}"
            ) from last_exception

        return wrapper
    return decorator

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")

    args = parser.parse_args()

    qm = QuotaManager()

    if args.status:
        print(qm.get_status())


if __name__ == "__main__":
    main()

def check_daily_quota():
    """
    Backward compatibility wrapper for GitHub Actions.
    """
    from utils.quota_manager import QuotaManager

    qm = QuotaManager()
    qm._check_daily_quota()
