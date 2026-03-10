import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from app.agents.extractor import run_extractor
from app.agents.planner import build_execution_plan
from app.agents.report_writer import generate_formal_report
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _update_task_status(task_id: int, status: str) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    UPDATE tasks
                    SET status = :status, updated_at = NOW()
                    WHERE id = :task_id
                    """
                ),
                {"status": status, "task_id": task_id},
            )


async def _insert_agent_output(
    task_id: int,
    agent_name: str,
    output_json: dict[str, Any],
    confidence: float | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO agent_outputs (task_id, agent_name, output_json, confidence)
                    VALUES (:task_id, :agent_name, CAST(:output_json AS JSONB), :confidence)
                    """
                ),
                {
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "output_json": json.dumps(output_json),
                    "confidence": confidence,
                },
            )


async def _store_task_plan(task_id: int, plan: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    """
                    UPDATE tasks
                    SET plan_json = CAST(:plan_json AS JSONB), updated_at = NOW()
                    WHERE id = :task_id
                    """
                ),
                {
                    "task_id": task_id,
                    "plan_json": json.dumps(plan),
                },
            )


async def _get_task_input(task_id: int) -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT input_text FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        )
        input_text = result.scalar_one_or_none()
        if input_text is None:
            raise ValueError(f"Task {task_id} not found while loading planner input")
        return str(input_text)


def _build_formal_summary_report(
    task_input: str,
    extractor_output: dict[str, Any],
) -> dict[str, Any]:
    company = extractor_output.get("company_name") or "Unknown Company"
    ticker = extractor_output.get("ticker")
    key_points = extractor_output.get("key_points") or []
    facts = extractor_output.get("facts") or {}

    top_points = [str(point) for point in key_points[:5]]
    fact_lines = [f"{key}: {value}" for key, value in facts.items()]

    executive_summary = (
        f"This report evaluates {company}"
        + (f" ({ticker})" if ticker else "")
        + " based on the provided investment context and extracted fundamentals."
    )
    thesis = (
        "The current thesis is based on qualitative extraction and preliminary fact signals. "
        "A full financial/market/risk multi-agent pass should be completed before decisioning."
    )
    risk_assessment = (
        "Key risks include incomplete data coverage, model uncertainty, and "
        "potential mismatch between extracted facts and real-time market conditions."
    )

    return {
        "title": "Investment Analysis Report",
        "subject": company,
        "executive_summary": executive_summary,
        "input_context": task_input,
        "highlights": top_points,
        "observed_facts": fact_lines,
        "investment_thesis": thesis,
        "risk_assessment": risk_assessment,
        "recommendation": "HOLD",
        "confidence_note": "Preliminary recommendation generated from partial agent execution.",
        "disclaimer": "For research support only. Not financial advice.",
    }


def _build_fallback_report_text(formal_report: dict[str, Any]) -> str:
    highlights = formal_report.get("highlights") or []
    observed_facts = formal_report.get("observed_facts") or []

    highlights_block = "\n".join(f"- {item}" for item in highlights) if highlights else "- Not available"
    facts_block = "\n".join(f"- {item}" for item in observed_facts) if observed_facts else "- Not available"

    return (
        f"Title: {formal_report.get('title', 'Investment Analysis Report')}\n\n"
        "1. Executive Summary\n"
        f"{formal_report.get('executive_summary', 'Not available.')}\n\n"
        "2. Company Overview\n"
        f"Company: {formal_report.get('subject', 'Unknown Company')}\n"
        f"Ticker: {formal_report.get('ticker', 'N/A')}\n\n"
        "3. Key Highlights\n"
        f"{highlights_block}\n\n"
        "4. Market Context\n"
        "Market context is limited in the current agent pass.\n\n"
        "5. Observed Facts\n"
        f"{facts_block}\n\n"
        "6. Risk Assessment\n"
        f"{formal_report.get('risk_assessment', 'Not available.')}\n\n"
        "7. Investment Thesis\n"
        f"{formal_report.get('investment_thesis', 'Not available.')}\n\n"
        "8. Recommendation\n"
        f"{formal_report.get('recommendation', 'HOLD')}\n"
        f"{formal_report.get('confidence_note', '')}\n\n"
        "9. Disclaimer\n"
        f"{formal_report.get('disclaimer', 'For research support only. Not financial advice.')}"
    )


async def run_task_pipeline(task_id: int) -> None:
    """
    Simulated async orchestration pipeline.
    Transitions task state through planning and execution phases.
    """
    try:
        await _update_task_status(task_id, "PLANNING")
        await asyncio.sleep(1)
        task_input = await _get_task_input(task_id)
        plan = await build_execution_plan(task_context=task_input)
        await _store_task_plan(task_id, plan.model_dump())
        await _insert_agent_output(
            task_id=task_id,
            agent_name="planner",
            output_json={"plan": plan.model_dump()},
            confidence=0.92,
        )

        await _update_task_status(task_id, "RUNNING")
        await asyncio.sleep(1)
        extractor_output = await run_extractor(task_input)
        await _insert_agent_output(
            task_id=task_id,
            agent_name="extractor",
            output_json=extractor_output.model_dump(),
            confidence=0.90,
        )
        formal_report = _build_formal_summary_report(task_input, extractor_output.model_dump())
        await _insert_agent_output(
            task_id=task_id,
            agent_name="summary",
            output_json=formal_report,
            confidence=0.85,
        )
        report_writer_input = [
            {"agent_name": "planner", "output_json": {"plan": plan.model_dump()}},
            {"agent_name": "extractor", "output_json": extractor_output.model_dump()},
            {"agent_name": "summary", "output_json": formal_report},
        ]
        try:
            report_text = await generate_formal_report(report_writer_input)
        except Exception:
            logger.exception("Report writer failed for task_id=%s. Using fallback text.", task_id)
            report_text = _build_fallback_report_text(formal_report)

        await _insert_agent_output(
            task_id=task_id,
            agent_name="report_writer",
            output_json={"report_text": report_text},
            confidence=0.88,
        )

        await _update_task_status(task_id, "COMPLETED")
    except Exception:
        logger.exception("Task pipeline failed for task_id=%s", task_id)
        await _update_task_status(task_id, "FAILED")
