import json

import pytest

from app.services.llm_service import LLMInvalidJSONError, LLMService


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self._index = 0

    async def post(self, url: str, json: dict) -> _FakeResponse:
        _ = (url, json)
        output = self._outputs[min(self._index, len(self._outputs) - 1)]
        self._index += 1
        return _FakeResponse({"response": output, "prompt_eval_count": 10, "eval_count": 20})


@pytest.mark.asyncio
async def test_generate_json_retries_and_succeeds() -> None:
    client = _FakeClient(outputs=["not json", '{"ok": true}'])
    service = LLMService(client=client, json_retry_attempts=3)

    result = await service.generate(prompt="return json", expect_json=True)
    assert isinstance(result, dict)
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_generate_json_raises_after_retry_exhausted() -> None:
    client = _FakeClient(outputs=["invalid", "still invalid", "also invalid"])
    service = LLMService(client=client, json_retry_attempts=3)

    with pytest.raises(LLMInvalidJSONError):
        await service.generate(prompt="return json", expect_json=True)


@pytest.mark.asyncio
async def test_generate_text_returns_raw_string() -> None:
    text = "plain text answer"
    client = _FakeClient(outputs=[text])
    service = LLMService(client=client, json_retry_attempts=3)

    result = await service.generate(prompt="return text", expect_json=False)
    assert result == text
