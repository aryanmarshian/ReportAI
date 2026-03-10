import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Base exception for LLM service failures."""


class LLMTimeoutError(LLMServiceError):
    """Raised when the LLM request times out."""


class LLMAPIError(LLMServiceError):
    """Raised when the LLM API returns an error response."""


class LLMInvalidJSONError(LLMServiceError):
    """Raised when JSON output remains invalid after retry attempts."""

    def __init__(self, message: str, attempts: int, raw_response: str) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.raw_response = raw_response


class LLMService:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        json_retry_attempts: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
        self.timeout_seconds = float(timeout_seconds or os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
        self.json_retry_attempts = json_retry_attempts
        self._client = client

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        expect_json: bool = False,
    ) -> dict[str, Any] | str:
        attempts = self.json_retry_attempts if expect_json else 1
        last_raw = ""

        for attempt in range(1, attempts + 1):
            effective_prompt = self._build_prompt(prompt=prompt, expect_json=expect_json, attempt=attempt)
            payload = self._build_payload(
                prompt=effective_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                expect_json=expect_json,
            )

            response = await self._request_ollama(payload=payload)
            raw_text = self._extract_text(response)
            self._log_usage(response)
            last_raw = raw_text

            if not expect_json:
                return raw_text

            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                logger.warning(
                    "Invalid JSON from model '%s' on attempt %s/%s",
                    self.model,
                    attempt,
                    attempts,
                )

        raise LLMInvalidJSONError(
            message="Model failed to produce valid JSON after retries",
            attempts=attempts,
            raw_response=last_raw,
        )

    def _build_prompt(self, prompt: str, expect_json: bool, attempt: int) -> str:
        if not expect_json:
            return prompt
        retry_note = ""
        if attempt > 1:
            retry_note = (
                f"\nRetry attempt {attempt}: previous output was invalid JSON. "
                "Return only a valid JSON object."
            )
        return (
            "Return only strict JSON. Do not include markdown, code fences, or commentary.\n"
            f"{prompt}{retry_note}"
        )

    def _build_payload(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        expect_json: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if expect_json:
            payload["format"] = "json"
        return payload

    async def _request_ollama(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/generate"
        timeout = httpx.Timeout(timeout=self.timeout_seconds)

        if self._client is not None:
            return await self._post(self._client, url, payload)

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await self._post(client, url, payload)

    async def _post(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds} seconds"
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            raise LLMAPIError(f"Ollama returned HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise LLMAPIError(f"Ollama request failed: {exc}") from exc

        data = resp.json()
        if "error" in data:
            raise LLMAPIError(f"Ollama error: {data['error']}")
        return data

    def _extract_text(self, response: dict[str, Any]) -> str:
        text = response.get("response")
        if not isinstance(text, str) or not text.strip():
            raise LLMAPIError("Ollama response missing 'response' text")
        return text.strip()

    def _log_usage(self, response: dict[str, Any]) -> None:
        prompt_tokens = response.get("prompt_eval_count")
        completion_tokens = response.get("eval_count")
        if prompt_tokens is not None or completion_tokens is not None:
            logger.info(
                "LLM usage model=%s prompt_tokens=%s completion_tokens=%s total_duration_ns=%s",
                self.model,
                prompt_tokens,
                completion_tokens,
                response.get("total_duration"),
            )
