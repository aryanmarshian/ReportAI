import json
from typing import Any

from app.services.llm_service import LLMService

REPORT_WRITER_PROMPT_TEMPLATE = """You are a professional financial research report writer.

You will be given a JSON object containing outputs from multiple analysis agents (such as planner, extractor, financial, market, risk, and summary). Your task is to convert this structured JSON information into a clear, professional, well-written investment research report.

Follow these rules strictly:

1. DO NOT modify or invent facts that are not present in the JSON.
2. Extract all relevant information from the JSON fields such as:
   - company_name
   - ticker
   - key_points
   - facts
   - observed_facts
   - highlights
   - recommendation
   - risk_assessment
   - investment_thesis
   - executive_summary
   - input_context
3. Merge information from different agents into a coherent narrative.
4. Write the report in clear professional language suitable for an investment analysis document.

The report must follow this structure:

Title: Investment Analysis Report

Sections:
1. Executive Summary
   - Brief explanation of the investment question
   - Overview of the company and conclusion

2. Company Overview
   - Company name
   - Ticker
   - Description using extracted key points

3. Key Highlights
   - Bullet points summarizing important company insights

4. Market Context
   - Industry positioning and competition (if mentioned)

5. Observed Facts
   - Important metrics such as market capitalization

6. Risk Assessment
   - Summarize risks mentioned in the JSON

7. Investment Thesis
   - Explain the reasoning behind the analysis

8. Recommendation
   - Clearly state the recommendation (BUY / HOLD / SELL)
   - Mention confidence notes if provided

9. Disclaimer
   - Include the disclaimer from the JSON

Formatting rules:
- Use professional paragraphs and headings
- Convert lists into clean bullet points where appropriate
- Ensure the report reads naturally like a financial research report
- Do not output JSON
- Output only the final formatted report

Here is the JSON input:

{JSON_INPUT}
"""


def _build_prompt(agent_outputs: list[dict[str, Any]]) -> str:
    input_payload = {"agent_outputs": agent_outputs}
    return REPORT_WRITER_PROMPT_TEMPLATE.replace(
        "{JSON_INPUT}",
        json.dumps(input_payload, indent=2, ensure_ascii=True),
    )


async def generate_formal_report(
    agent_outputs: list[dict[str, Any]],
    llm_service: LLMService | None = None,
) -> str:
    service = llm_service or LLMService()
    prompt = _build_prompt(agent_outputs)

    last_text = ""
    for _ in range(3):
        text = await service.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=2200,
            expect_json=False,
        )
        if isinstance(text, str):
            stripped = text.strip()
            if stripped:
                return stripped
            last_text = stripped

    raise RuntimeError(f"Report writer failed after 3 attempts. Last output: {last_text}")
