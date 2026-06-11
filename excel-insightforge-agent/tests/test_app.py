"""Unit & smoke tests for Excel InsightForge Agent.

Run:  pytest -q
"""

import pandas as pd

from config import resolve_api_key
from services import analytics, dataset_generator
from services.ai_service import _parse_action, agentic_answer


def _small_workbook():
    return dataset_generator.generate_workbook(
        n_orders=2_000, n_customers=300, n_products=50
    )


def test_config_analytics_mode(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = resolve_api_key(None)
    assert not cfg.ai_enabled
    assert cfg.mode == "Analytics Mode"


def test_config_sidebar_priority(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    cfg = resolve_api_key("sidebar-key")
    assert cfg.api_key == "sidebar-key"  # sidebar wins over env


def test_dataset_generator_shapes():
    wb = _small_workbook()
    assert set(wb) == {"Orders", "Customers", "Products", "Marketing", "SupplyChain"}
    assert len(wb["Orders"]) == 2_000
    assert {"revenue", "profit", "region"} <= set(wb["Orders"].columns)


def test_profile_and_kpis():
    wb = _small_workbook()
    profiles = analytics.profile_workbook(wb)
    assert len(profiles) == 5
    kpis = analytics.generate_kpis(wb)
    assert kpis["total_revenue"] > 0
    assert "profit_margin_pct" in kpis
    assert "top_regions" in kpis
    assert "marketing_roi" in kpis


def test_trend_and_forecast():
    wb = _small_workbook()
    trend = analytics.monthly_trend(wb["Orders"])
    assert trend is not None and len(trend) >= 3
    fc = analytics.linear_forecast(trend, periods=6)
    assert (fc["kind"] == "forecast").sum() == 6
    assert (fc["value"] >= 0).all()


def test_rule_based_summary_no_ai():
    wb = _small_workbook()
    kpis = analytics.generate_kpis(wb)
    text = analytics.rule_based_summary(kpis, wb)
    assert "Executive Summary" in text
    assert "revenue" in text.lower()


def test_agentic_answer_fallback_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = resolve_api_key(None)
    wb = _small_workbook()
    kpis = analytics.generate_kpis(wb)
    out = agentic_answer(cfg, "What drives revenue?", wb, kpis)
    assert "Analytics Mode" in out["answer"]
    assert out["steps"] == []


def test_parse_action():
    assert _parse_action('noise {"action": "final", "answer": "hi"} tail') == {
        "action": "final",
        "answer": "hi",
    }
    assert _parse_action("no json here") is None


def test_excel_roundtrip(tmp_path):
    wb = _small_workbook()
    data = dataset_generator.workbook_to_excel_bytes(
        {"Orders": wb["Orders"].head(100)}
    )
    p = tmp_path / "t.xlsx"
    p.write_bytes(data)
    back = pd.read_excel(p, sheet_name="Orders")
    assert len(back) == 100
