from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session, ping_db
from app.services.task_runner import run_task_pipeline


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(title="reportai", lifespan=lifespan)
FRONTEND_DIR = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


class AnalyzeRequest(BaseModel):
    user_id: int = Field(default=1, ge=1)
    input_text: str = Field(
        default="Analyze this investment opportunity with focus on valuation and risk.",
        min_length=5,
        max_length=4000,
    )


class AnalyzeResponse(BaseModel):
    task_id: int
    status: str


class StatusResponse(BaseModel):
    status: str


class PlanResponse(BaseModel):
    task_id: int
    status: str
    plan: dict[str, Any]


class ReportAgentOutput(BaseModel):
    agent_name: str
    output_json: Any
    confidence: float | None = None
    created_at: str


class ReportResponse(BaseModel):
    task_id: int
    status: str
    plan: dict[str, Any]
    formal_report: dict[str, Any]
    formal_report_text: str
    report: list[ReportAgentOutput]


def _fallback_formal_report(task_row: dict[str, Any], report: list[ReportAgentOutput]) -> dict[str, Any]:
    input_context = str(task_row.get("input_text") or "")
    extractor = next((r for r in report if r.agent_name == "extractor"), None)
    extractor_payload = extractor.output_json if extractor else {}
    company = "Unknown Company"
    ticker = None
    highlights: list[str] = []
    observed_facts: list[str] = []

    if isinstance(extractor_payload, dict):
        company = str(extractor_payload.get("company_name") or company)
        ticker = extractor_payload.get("ticker")
        kp = extractor_payload.get("key_points")
        if isinstance(kp, list):
            highlights = [str(x) for x in kp[:5]]
        facts = extractor_payload.get("facts")
        if isinstance(facts, dict):
            observed_facts = [f"{k}: {v}" for k, v in facts.items()]

    return {
        "title": "Investment Analysis Report",
        "subject": company,
        "executive_summary": (
            f"This report evaluates {company}" + (f" ({ticker})" if ticker else "") + "."
        ),
        "input_context": input_context,
        "highlights": highlights,
        "observed_facts": observed_facts,
        "investment_thesis": "Preliminary thesis based on currently completed agents.",
        "risk_assessment": "Risk assessment is preliminary and should be validated with full agent coverage.",
        "recommendation": "HOLD",
        "confidence_note": "Model-generated draft. Review before decisions.",
        "disclaimer": "For research support only. Not financial advice.",
    }


def _fallback_formal_report_text(formal_report: dict[str, Any]) -> str:
    highlights = formal_report.get("highlights") or []
    observed_facts = formal_report.get("observed_facts") or []
    highlights_block = "\n".join(f"- {item}" for item in highlights) if highlights else "- Not available"
    facts_block = "\n".join(f"- {item}" for item in observed_facts) if observed_facts else "- Not available"

    return (
        f"Title: {formal_report.get('title', 'Investment Analysis Report')}\n\n"
        "1. Executive Summary\n"
        f"{formal_report.get('executive_summary', 'Not available.')}\n\n"
        "2. Company Overview\n"
        f"Company: {formal_report.get('subject', 'Unknown Company')}\n\n"
        "3. Key Highlights\n"
        f"{highlights_block}\n\n"
        "4. Market Context\n"
        "Market context is limited in the current run.\n\n"
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


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    try:
        if not await ping_db():
            raise HTTPException(status_code=503, detail="Database ping failed")

        await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> AnalyzeResponse:
    try:
        async with session.begin():
            result = await session.execute(
                text(
                    """
                    INSERT INTO tasks (user_id, input_text, status)
                    VALUES (:user_id, :input_text, :status)
                    RETURNING id
                    """
                ),
                {
                    "user_id": payload.user_id,
                    "input_text": payload.input_text,
                    "status": "QUEUED",
                },
            )
            task_id = result.scalar_one()

        background_tasks.add_task(run_task_pipeline, task_id)
        return AnalyzeResponse(task_id=task_id, status="queued")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to create task: {exc}") from exc


@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(
    task_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> StatusResponse:
    result = await session.execute(
        text("SELECT status FROM tasks WHERE id = :task_id"),
        {"task_id": task_id},
    )
    status = result.scalar_one_or_none()

    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return StatusResponse(status=str(status).lower())


@app.get("/plan/{task_id}", response_model=PlanResponse)
async def get_plan(
    task_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> PlanResponse:
    result = await session.execute(
        text("SELECT status, plan_json FROM tasks WHERE id = :task_id"),
        {"task_id": task_id},
    )
    row = result.mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    plan_json = row["plan_json"] or {}
    if not isinstance(plan_json, dict):
        raise HTTPException(status_code=500, detail="Invalid plan format in DB")

    return PlanResponse(
        task_id=task_id,
        status=str(row["status"]).lower(),
        plan=plan_json,
    )


@app.get("/report/{task_id}", response_model=ReportResponse)
async def get_report(
    task_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ReportResponse:
    task_result = await session.execute(
        text("SELECT status, plan_json, input_text FROM tasks WHERE id = :task_id"),
        {"task_id": task_id},
    )
    task_row = task_result.mappings().first()

    if task_row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task_row["status"]
    if str(status).upper() != "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=f"Task is not completed yet. Current status: {str(status).lower()}",
        )

    outputs_result = await session.execute(
        text(
            """
            SELECT agent_name, output_json, confidence, created_at
            FROM agent_outputs
            WHERE task_id = :task_id
            ORDER BY created_at ASC
            """
        ),
        {"task_id": task_id},
    )
    rows = outputs_result.mappings().all()

    report = [
        ReportAgentOutput(
            agent_name=str(row["agent_name"]),
            output_json=row["output_json"],
            confidence=(
                float(row["confidence"])
                if isinstance(row["confidence"], Decimal)
                else row["confidence"]
            ),
            created_at=row["created_at"].isoformat(),
        )
        for row in rows
    ]

    plan_json = task_row["plan_json"] or {}
    if not isinstance(plan_json, dict):
        raise HTTPException(status_code=500, detail="Invalid plan format in DB")

    summary_entry = next((item for item in report if item.agent_name == "summary"), None)
    summary_payload = summary_entry.output_json if summary_entry else None
    if isinstance(summary_payload, dict) and summary_payload.get("executive_summary"):
        formal_report = summary_payload
    else:
        formal_report = _fallback_formal_report(task_row, report)

    report_writer_entry = next((item for item in report if item.agent_name == "report_writer"), None)
    report_writer_payload = report_writer_entry.output_json if report_writer_entry else None
    formal_report_text = ""
    if isinstance(report_writer_payload, dict):
        maybe_text = report_writer_payload.get("report_text")
        if isinstance(maybe_text, str) and maybe_text.strip():
            formal_report_text = maybe_text.strip()
    if not formal_report_text:
        formal_report_text = _fallback_formal_report_text(formal_report)

    return ReportResponse(
        task_id=task_id,
        status=str(status).lower(),
        plan=plan_json,
        formal_report=formal_report,
        formal_report_text=formal_report_text,
        report=report,
    )
