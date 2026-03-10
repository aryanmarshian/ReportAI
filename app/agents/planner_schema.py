from typing import Literal

from pydantic import BaseModel, Field, field_validator

AllowedAgentName = Literal["extractor", "financial", "market", "risk", "summary"]


class PlannerAgent(BaseModel):
    name: AllowedAgentName
    objective: str = Field(min_length=5, max_length=240)
    priority: int = Field(ge=1, le=10)


class PlannerPlan(BaseModel):
    agents: list[PlannerAgent] = Field(min_length=1, max_length=10)
    notes: str | None = Field(default=None, max_length=400)

    @field_validator("agents")
    @classmethod
    def validate_unique_agent_names(cls, value: list[PlannerAgent]) -> list[PlannerAgent]:
        names = [agent.name for agent in value]
        if len(names) != len(set(names)):
            raise ValueError("Agent names in plan must be unique")
        return value


def default_planner_plan() -> PlannerPlan:
    return PlannerPlan(
        agents=[
            PlannerAgent(
                name="extractor",
                objective="Extract key financial and qualitative facts from the input.",
                priority=1,
            ),
            PlannerAgent(
                name="financial",
                objective="Evaluate valuation, profitability, growth, and cash flow quality.",
                priority=2,
            ),
            PlannerAgent(
                name="market",
                objective="Assess industry context, macro trends, and competitive position.",
                priority=3,
            ),
            PlannerAgent(
                name="risk",
                objective="Identify downside scenarios, red flags, and uncertainty factors.",
                priority=4,
            ),
            PlannerAgent(
                name="summary",
                objective="Consolidate outputs into a final investment recommendation summary.",
                priority=5,
            ),
        ],
        notes="Deterministic fallback planner output.",
    )
