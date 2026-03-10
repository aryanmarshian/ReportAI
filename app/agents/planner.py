from app.agents.planner_prompt import build_planner_prompts
from app.agents.planner_schema import PlannerPlan
from app.services.llm_service import LLMInvalidJSONError, LLMService


async def build_execution_plan(task_context: str) -> PlannerPlan:
    system_prompt, user_prompt = build_planner_prompts(task_context)
    prompt = f"{system_prompt}\n\n{user_prompt}"

    llm_service = LLMService()
    payload = await llm_service.generate(
        prompt=prompt,
        temperature=0.1,
        max_tokens=1200,
        expect_json=True,
    )
    if not isinstance(payload, dict):
        raise LLMInvalidJSONError(
            message="Planner expected JSON object but received non-object response",
            attempts=1,
            raw_response=str(payload),
        )
    return PlannerPlan.model_validate(payload)
