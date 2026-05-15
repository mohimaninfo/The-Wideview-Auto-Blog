"""
utils/gemini_client.py

Clean Gemini API wrapper using the new google-genai SDK.

Features:
- Simple client interface
- Model support (no hardcoded preview models)
- Optional JSON mode
- Retry handling
- System instruction support
"""

import os
import time
import random
import logging
from typing import Any, Optional

import requests  # noqa: F401 — tests patch utils.gemini_client.requests.post

from google import genai

from config.settings import GeminiConfig
from google.api_core.exceptions import ResourceExhausted

logger = logging.getLogger(__name__)


def smart_gemini_call(prompt: str, primary_model: str, fallback_model: str = "gemini-2.5-flash", **kwargs):
    """
    Robust Gemini call with automatic fallback on quota exhaustion.
    """

    client = GeminiClient()

    try:
        return client.generate(prompt, model=primary_model, **kwargs)

    except Exception as e:
        error_str = str(e)

        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            logger.warning(
                f"[FALLBACK] {primary_model} exhausted → switching to {fallback_model}"
            )

            return client.generate(prompt, model=fallback_model, **kwargs)

        raise

def call_gemini(prompt: str, model: Optional[str] = None, **kwargs: Any) -> str:
    """
    Module-level helper used across agents. Forwards kwargs to GeminiClient.generate
    (e.g. system_instruction, json_mode, temperature, max_tokens / max_output_tokens).
    """
    gen_kwargs = dict(kwargs)
    if "max_tokens" in gen_kwargs:
        gen_kwargs["max_output_tokens"] = gen_kwargs.pop("max_tokens")
    use_model = model or gen_kwargs.pop("model", None)
    client = GeminiClient(model=use_model)
    return client.generate(prompt, model=use_model, **gen_kwargs)


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key (or uses GEMINI_API_KEY env var)
            model: Default model to use
            max_retries: Retry attempts on failure
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.model = model or GeminiConfig.PRIMARY_MODEL
        self.max_retries = max_retries

        self.client = genai.Client(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> str:
        """
        Generate text from Gemini model.

        Args:
            prompt: User prompt
            system_instruction: Optional system instruction
            model: Override default model
            json_mode: Force JSON output
            temperature: Creativity control
            max_output_tokens: Response length limit

        Returns:
            Model response text
        """

        use_model = model or self.model

        config = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        if json_mode:
            config["response_mime_type"] = "application/json"

        if system_instruction:
            config["system_instruction"] = system_instruction

        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=use_model,
                    contents=prompt,
                    config=config,
                )

                text = getattr(response, "text", None)
                if not text:
                    raise RuntimeError("Empty response from Gemini")

                logger.info(f"Gemini success | model={use_model} | attempt={attempt + 1}")
                return text

            except Exception as e:
                last_error = e
                wait_time = (2 ** attempt) + random.uniform(0, 1)

                logger.warning(
                    f"Gemini attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait_time:.1f}s"
                )

                time.sleep(min(wait_time, 30))

        raise RuntimeError(
            f"Gemini request failed after {self.max_retries} attempts: {last_error}"
        )
