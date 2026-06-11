"""
AI service for Excel InsightForge Agent.

Two responsibilities:
1. LLM-narrated executive summaries via Groq (LangChain ChatGroq).
2. An *agentic* Data Q&A loop: the LLM plans which analytics TOOLS to
   call (KPIs, group-by, trend, forecast, anomalies...), observes the
   results, and only then answers — a minimal ReAct-style agent that
   makes the "Agentic AI" part of the FDP tangible.

Everything degrades gracefully: if no API key, callers fall back to
rule-based outputs from services.analytics.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from config import AIConfig
from services import analytics

logger = logging.getLogger("insightforge.ai")

MAX_AGENT_STEPS = 5


# --------------------------------------------------------------------------- #
# LLM factory
# --------------------------------------------------------------------------- #
def get_llm(cfg: AIConfig):
    """Create a LangChain ChatGroq client. Returns None on any failure."""
    if not cfg.ai_enabled:
        return None
    try:
        from langchain_groq import ChatGroq

        return ChatGroq(model=cfg.model, api_key=cfg.api_key, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialise Groq LLM: %s", exc)
        return None


def _invoke(llm, prompt: str) -> Optional[str]:
    """Single LLM call with defensive error handling."""
    try:
        resp = llm.invoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM invocation failed: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Executive summary
# --------------------------------------------------------------------------- #
def ai_executive_summary(
    cfg: AIConfig, kpis: Dict[str, Any], profiles: List[Dict[str, Any]]
) -> Optional[str]:
    """LLM-written executive summary. None -> caller uses rule-based."""
    llm = get_llm(cfg)
    if llm is None:
        return None
    public_kpis = {k: v for k, v in kpis.items() if not k.startswith("_")}
    prompt = f"""You are a senior business analyst presenting to executives.

DATASET PROFILE (per sheet):
{json.dumps(profiles, indent=2, default=str)[:3000]}

COMPUTED KPIs:
{json.dumps(public_kpis, indent=2, default=str)[:3000]}

Write a crisp markdown report with EXACTLY these sections:
## Executive Summary  (3-4 sentences)
## Key Insights        (4-6 bullets, cite numbers)
## Business Recommendations (3-5 actionable bullets)
## Risk Assessment     (2-3 bullets)
## Growth Opportunities (2-3 bullets)

Be specific and quantitative. Do not invent numbers not present above."""
    return _invoke(llm, prompt)


# --------------------------------------------------------------------------- #
# Agentic Data Q&A — minimal ReAct-style tool loop
# --------------------------------------------------------------------------- #
def _build_tools(
    sheets: Dict[str, pd.DataFrame], kpis: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Registry of analytics tools the agent may call.

    Each tool: {"description": str, "fn": Callable[[dict], str]}.
    Tools return JSON strings (observations) for the agent.
    """

    def list_sheets(_: dict) -> str:
        return json.dumps(
            {
                n: {"rows": len(d), "columns": list(map(str, d.columns))[:25]}
                for n, d in sheets.items()
            }
        )

    def get_kpis(_: dict) -> str:
        return json.dumps(
            {k: v for k, v in kpis.items() if not k.startswith("_")}, default=str
        )

    def group_aggregate(args: dict) -> str:
        df = sheets.get(args.get("sheet", ""))
        if df is None:
            return json.dumps({"error": f"unknown sheet {args.get('sheet')}"})
        by, val = args.get("group_by"), args.get("value_column")
        agg = args.get("agg", "sum")
        if by not in df.columns or val not in df.columns:
            return json.dumps({"error": "unknown column", "columns": list(df.columns)})
        try:
            out = getattr(df.groupby(by)[val], agg)().sort_values(ascending=False)
            return out.head(15).round(2).to_json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    def trend_and_forecast(args: dict) -> str:
        df = sheets.get(args.get("sheet", ""))
        if df is None:
            return json.dumps({"error": f"unknown sheet {args.get('sheet')}"})
        trend = analytics.monthly_trend(df)
        if trend is None:
            return json.dumps({"error": "no date+revenue columns found"})
        fc = analytics.linear_forecast(trend)
        fc["month"] = fc["month"].dt.strftime("%Y-%m")
        return fc.round(0).to_json(orient="records")

    def anomalies(args: dict) -> str:
        df = sheets.get(args.get("sheet", ""))
        if df is None:
            return json.dumps({"error": f"unknown sheet {args.get('sheet')}"})
        return json.dumps(analytics.detect_anomalies(df))

    def declining(args: dict) -> str:
        df = sheets.get(args.get("sheet", ""))
        if df is None:
            return json.dumps({"error": f"unknown sheet {args.get('sheet')}"})
        return json.dumps({"declining_products": analytics.declining_products(df)})

    return {
        "list_sheets": {
            "description": "List all sheets with row counts and column names. "
            "Args: {}",
            "fn": list_sheets,
        },
        "get_kpis": {
            "description": "Return all pre-computed business KPIs. Args: {}",
            "fn": get_kpis,
        },
        "group_aggregate": {
            "description": "Aggregate a value column grouped by another column. "
            'Args: {"sheet": str, "group_by": str, "value_column": str, '
            '"agg": "sum|mean|count"}',
            "fn": group_aggregate,
        },
        "trend_and_forecast": {
            "description": "Monthly revenue trend + 6-month linear forecast. "
            'Args: {"sheet": str}',
            "fn": trend_and_forecast,
        },
        "anomalies": {
            "description": "Detect months with anomalous revenue (z-score). "
            'Args: {"sheet": str}',
            "fn": anomalies,
        },
        "declining_products": {
            "description": "Find products with >25% revenue decline. "
            'Args: {"sheet": str}',
            "fn": declining,
        },
    }


def _parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from the LLM's reply."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def agentic_answer(
    cfg: AIConfig,
    question: str,
    sheets: Dict[str, pd.DataFrame],
    kpis: Dict[str, Any],
) -> Dict[str, Any]:
    """Answer a data question via an agentic tool-use loop.

    Returns {"answer": str, "steps": [{"tool", "args", "observation"}...]}
    so the UI can show the agent's reasoning trace — great for teaching.
    """
    llm = get_llm(cfg)
    tools = _build_tools(sheets, kpis)
    steps: List[Dict[str, Any]] = []

    if llm is None:
        # Analytics-mode fallback: answer directly from KPIs.
        return {
            "answer": "🟡 **Analytics Mode** — AI chat needs a Groq API key.\n\n"
            "Here are the computed KPIs instead:\n```json\n"
            + json.dumps(
                {k: v for k, v in kpis.items() if not k.startswith("_")},
                indent=2,
                default=str,
            )
            + "\n```",
            "steps": steps,
        }

    tool_desc = "\n".join(f"- {n}: {t['description']}" for n, t in tools.items())
    scratchpad = ""

    for step in range(MAX_AGENT_STEPS):
        prompt = f"""You are a data-analysis agent. Answer the user's question by
calling tools, then give a final answer grounded ONLY in observations.

TOOLS:
{tool_desc}

Respond with EXACTLY ONE JSON object, nothing else:
  {{"action": "<tool_name>", "args": {{...}}}}        to call a tool
  {{"action": "final", "answer": "<markdown answer>"}} when done

QUESTION: {question}

PREVIOUS STEPS:
{scratchpad or "(none yet)"}

JSON:"""
        raw = _invoke(llm, prompt)
        if raw is None:
            break
        action = _parse_action(raw)
        if action is None:
            # Model answered in prose — accept it as final.
            return {"answer": raw, "steps": steps}

        if action.get("action") == "final":
            return {"answer": action.get("answer", ""), "steps": steps}

        name = action.get("action", "")
        args = action.get("args", {}) or {}
        tool = tools.get(name)
        obs = (
            tool["fn"](args)
            if tool
            else json.dumps({"error": f"unknown tool '{name}'"})
        )
        obs_short = obs[:1500]
        steps.append({"tool": name, "args": args, "observation": obs_short})
        scratchpad += f"\nStep {step + 1}: called {name}({args})\nObservation: {obs_short}\n"

    # Step budget exhausted — ask for a best-effort final answer.
    final = _invoke(
        llm,
        f"Question: {question}\n\nObservations so far:\n{scratchpad}\n\n"
        "Give your best final answer in markdown.",
    )
    return {"answer": final or "Unable to produce an answer.", "steps": steps}
