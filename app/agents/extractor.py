from pydantic import BaseModel, Field

from app.services.llm_service import LLMInvalidJSONError, LLMService


class ExtractorOutput(BaseModel):
    company_name: str = Field(min_length=1)
    ticker: str | None = None
    key_points: list[str] = Field(default_factory=list, max_length=20)
    facts: dict[str, str | float | int | None] = Field(default_factory=dict)


def build_extractor_prompt(task_context: str) -> str:
    return (
        "You are the extractor agent in an investment analysis system.\n"
        "Extract verifiable facts from the input context.\n"
        "Return only strict JSON object (no markdown/code fences/comments).\n"
        "If a field is unknown, use null or an empty array/object.\n"
        "Output JSON only with this exact shape and keys:\n"
        '{\n'
        '  "company_name": "string",\n'
        '  "ticker": "string or null",\n'
        '  "key_points": ["string"],\n'
        '  "facts": {"metric": "value"}\n'
        "}\n"
        "Context:\n"
        f"{task_context}"
    )


def _normalize_extractor_payload(payload: dict) -> dict:
    """
    Coerce weak/nullable model output into schema-compatible shape.
    """
    normalized = dict(payload)

    company_name = normalized.get("company_name")
    if not isinstance(company_name, str) or not company_name.strip():
        normalized["company_name"] = "Unknown Company"

    ticker = normalized.get("ticker")
    if ticker is not None and not isinstance(ticker, str):
        normalized["ticker"] = str(ticker)

    key_points = normalized.get("key_points")
    if isinstance(key_points, list):
        normalized["key_points"] = [str(item).strip() for item in key_points if str(item).strip()]
    else:
        normalized["key_points"] = []

    facts = normalized.get("facts")
    if isinstance(facts, dict):
        cleaned_facts: dict[str, str | float | int | None] = {}
        for key, value in facts.items():
            clean_key = str(key).strip()
            if not clean_key:
                continue
            if isinstance(value, (str, int, float)) or value is None:
                cleaned_facts[clean_key] = value
            else:
                cleaned_facts[clean_key] = str(value)
        normalized["facts"] = cleaned_facts
    else:
        normalized["facts"] = {}

    return normalized


async def run_extractor(task_context: str, llm_service: LLMService | None = None) -> ExtractorOutput:
    service = llm_service or LLMService()
    payload = await service.generate(
        prompt=build_extractor_prompt(task_context),
        temperature=0.1,
        max_tokens=1500,
        expect_json=True,
    )
    if not isinstance(payload, dict):
        raise LLMInvalidJSONError(
            message="Extractor expected JSON object but received non-object response",
            attempts=1,
            raw_response=str(payload),
        )
    normalized_payload = _normalize_extractor_payload(payload)
    return ExtractorOutput.model_validate(normalized_payload)
