import json

from app.agents.planner_schema import PlannerPlan


def build_planner_prompts(task_context: str) -> tuple[str, str]:
    schema_json = json.dumps(PlannerPlan.model_json_schema(), indent=2)

    system_prompt = (
        "You are the planner agent for a multi-agent investment analysis system.\n"
        "Output requirements:\n"
        "1) Return only a single JSON object.\n"
        "2) No markdown, no code fences, no commentary.\n"
        "3) Allowed agent names only: extractor, financial, market, risk, summary.\n"
        "4) Include keys: agents, notes.\n"
        "5) Each agent must include: name, objective, priority."
    )

    user_prompt = (
        "Create a planning JSON for the following investment task.\n"
        "Keep objectives concrete and ordered by execution priority.\n\n"
        f"Task context:\n{task_context}\n\n"
        "Required JSON schema:\n"
        f"{schema_json}\n\n"
        'Example output format:\n{"agents":[{"name":"extractor","objective":"...","priority":1}],"notes":"..."}'
    )

    return system_prompt, user_prompt
