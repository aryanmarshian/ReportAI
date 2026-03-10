import json
import os
from typing import Protocol

from openai import AsyncOpenAI

from app.agents.planner_schema import default_planner_plan


class PlannerProvider(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...


class OpenAIPlannerProvider:
    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty completion content")
        return content


class MockPlannerProvider:
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        _ = (system_prompt, user_prompt)
        return json.dumps(default_planner_plan().model_dump())


def get_planner_provider() -> PlannerProvider:
    provider = os.getenv("PLANNER_PROVIDER", "mock").strip().lower()
    model = os.getenv("PLANNER_MODEL", "gpt-4o-mini")

    if provider == "mock":
        return MockPlannerProvider()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when PLANNER_PROVIDER=openai")
        return OpenAIPlannerProvider(model=model, api_key=api_key)

    if provider == "local":
        base_url = os.getenv("PLANNER_BASE_URL", "").strip()
        if not base_url:
            raise RuntimeError("PLANNER_BASE_URL is required when PLANNER_PROVIDER=local")
        # Local OpenAI-compatible backends often accept any non-empty key.
        api_key = os.getenv("PLANNER_API_KEY", "local-key")
        return OpenAIPlannerProvider(model=model, api_key=api_key, base_url=base_url)

    raise RuntimeError(f"Unsupported planner provider: {provider}")
