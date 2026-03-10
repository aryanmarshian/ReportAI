import pytest
from pydantic import ValidationError

from app.agents.planner_schema import PlannerPlan, default_planner_plan


def test_default_planner_plan_has_expected_agents() -> None:
    plan = default_planner_plan()
    names = [agent.name for agent in plan.agents]
    assert names == ["extractor", "financial", "market", "risk", "summary"]


def test_planner_plan_rejects_unknown_agent_name() -> None:
    with pytest.raises(ValidationError):
        PlannerPlan.model_validate(
            {
                "agents": [
                    {"name": "unknown", "objective": "bad agent", "priority": 1},
                ]
            }
        )
