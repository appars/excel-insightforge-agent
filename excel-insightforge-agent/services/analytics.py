"""
Analytics engine for Excel InsightForge Agent.

Pure-pandas analytics that work with ZERO AI dependencies:
profiling, KPIs, trend detection, naive forecasting, correlation,
anomaly detection, and a rule-based executive summary.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("insightforge.analytics")

# Column-name keywords used for semantic KPI detection
REVENUE_KEYS = ("revenue", "sales", "amount", "total_price", "gmv")
PROFIT_KEYS = ("profit", "margin_amount", "net_income")
COST_KEYS = ("cost", "expense", "spend", "cogs")
QTY_KEYS = ("quantity", "qty", "units")
DATE_KEYS = ("date", "time", "day", "month", "timestamp", "order_date")
REGION_KEYS = ("region", "country", "state", "city", "market", "zone")
PRODUCT_KEYS = ("product", "item", "sku", "category")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _find_col(df: pd.DataFrame, keys: tuple, numeric: bool = True) -> Optional[str]:
    """Return the first column whose name contains any keyword.

    With numeric=True only numeric columns match. With numeric=False,
    non-numeric (categorical) matches are preferred over numeric ones,
    so e.g. 'product_name' wins over 'product_id'.
    """
    fallback: Optional[str] = None
    for col in df.columns:
        low = str(col).lower()
        if any(k in low for k in keys):
            if pd.api.types.is_numeric_dtype(df[col]):
                if numeric:
                    return col
                fallback = fallback or col
            elif not numeric:
                return col
    return None if numeric else fallback


def find_date_col(df: pd.DataFrame) -> Optional[str]:
    """Detect a date-like column (by dtype, then by name + parse check)."""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    for col in df.columns:
        if any(k in str(col).lower() for k in DATE_KEYS):
            try:
                pd.to_datetime(df[col], errors="raise")
                return col
            except Exception:  # noqa: BLE001
                continue
    return None


# --------------------------------------------------------------------------- #
# Profiling
# --------------------------------------------------------------------------- #
def profile_sheet(df: pd.DataFrame, name: str) -> Dict[str, Any]:
    """Profile a single sheet: shape, dtypes, missing values, stats."""
    missing = df.isna().sum()
    profile: Dict[str, Any] = {
        "sheet": name,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2),
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "missing": {str(c): int(v) for c, v in missing.items() if v > 0},
        "missing_pct": round(100 * missing.sum() / max(df.size, 1), 2),
        "numeric_stats": {},
        "duplicate_rows": int(df.duplicated().sum()),
    }
    num = df.select_dtypes(include=np.number)
    if not num.empty:
        desc = num.describe().T
        profile["numeric_stats"] = {
            str(c): {
                "mean": round(float(r["mean"]), 2),
                "std": round(float(r["std"]), 2) if not np.isnan(r["std"]) else 0.0,
                "min": round(float(r["min"]), 2),
                "max": round(float(r["max"]), 2),
            }
            for c, r in desc.iterrows()
        }
    return profile


def profile_workbook(sheets: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Profile every sheet in the workbook."""
    return [profile_sheet(df, name) for name, df in sheets.items()]


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
def generate_kpis(sheets: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Auto-generate business KPIs from whichever sheets contain the signals."""
    kpis: Dict[str, Any] = {}

    for name, df in sheets.items():
        rev_col = _find_col(df, REVENUE_KEYS)
        profit_col = _find_col(df, PROFIT_KEYS)
        cost_col = _find_col(df, COST_KEYS)
        region_col = _find_col(df, REGION_KEYS, numeric=False)
        product_col = _find_col(df, PRODUCT_KEYS, numeric=False)
        date_col = find_date_col(df)

        if rev_col and "total_revenue" not in kpis:
            total_rev = float(df[rev_col].sum())
            kpis["total_revenue"] = total_rev
            kpis["avg_order_value"] = round(float(df[rev_col].mean()), 2)
            kpis["_revenue_sheet"] = name
            kpis["_revenue_col"] = rev_col

            if profit_col:
                total_profit = float(df[profit_col].sum())
                kpis["total_profit"] = total_profit
                if total_rev:
                    kpis["profit_margin_pct"] = round(100 * total_profit / total_rev, 2)
            elif cost_col:
                total_profit = total_rev - float(df[cost_col].sum())
                kpis["total_profit"] = total_profit
                if total_rev:
                    kpis["profit_margin_pct"] = round(100 * total_profit / total_rev, 2)

            # Growth %: first-half vs second-half revenue (by date if available)
            if date_col:
                tmp = df[[date_col, rev_col]].dropna().copy()
                tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
                tmp = tmp.dropna().sort_values(date_col)
                if len(tmp) >= 4:
                    half = len(tmp) // 2
                    first, second = tmp[rev_col][:half].sum(), tmp[rev_col][half:].sum()
                    if first:
                        kpis["growth_pct"] = round(100 * (second - first) / first, 2)

            if region_col:
                by_region = (
                    df.groupby(region_col)[rev_col].sum().sort_values(ascending=False)
                )
                kpis["top_regions"] = {
                    str(k): round(float(v), 2) for k, v in by_region.head(5).items()
                }
                kpis["bottom_region"] = str(by_region.index[-1])
                # Low-profit region detection
                if profit_col:
                    margins = df.groupby(region_col).apply(
                        lambda g: 100 * g[profit_col].sum() / max(g[rev_col].sum(), 1e-9),
                        include_groups=False,
                    )
                    kpis["region_margins_pct"] = {
                        str(k): round(float(v), 2)
                        for k, v in margins.sort_values().items()
                    }

            if product_col:
                by_prod = (
                    df.groupby(product_col)[rev_col].sum().sort_values(ascending=False)
                )
                kpis["top_products"] = {
                    str(k): round(float(v), 2) for k, v in by_prod.head(5).items()
                }

        low = name.lower()
        # Marketing ROI
        if "market" in low:
            spend = _find_col(df, ("spend", "cost", "budget"))
            ret = _find_col(df, ("revenue", "return", "attributed"))
            if spend and ret and float(df[spend].sum()):
                kpis["marketing_roi"] = round(
                    float(df[ret].sum()) / float(df[spend].sum()), 2
                )
                ch = _find_col(df, ("channel", "campaign"), numeric=False)
                if ch:
                    roi = df.groupby(ch).apply(
                        lambda g: g[ret].sum() / max(g[spend].sum(), 1e-9),
                        include_groups=False,
                    )
                    kpis["channel_roi"] = {
                        str(k): round(float(v), 2)
                        for k, v in roi.sort_values(ascending=False).items()
                    }

        # Inventory metrics
        if "supply" in low or "inventory" in low:
            stock = _find_col(df, ("stock", "inventory", "on_hand"))
            reorder = _find_col(df, ("reorder", "threshold", "safety"))
            if stock is not None:
                kpis["total_inventory_units"] = int(df[stock].sum())
                if reorder is not None:
                    shortages = int((df[stock] < df[reorder]).sum())
                    kpis["items_below_reorder_point"] = shortages
            lead = _find_col(df, ("lead_time", "delay"))
            if lead:
                kpis["avg_lead_time_days"] = round(float(df[lead].mean()), 1)

    if "total_customers" not in kpis:
        for name, df in sheets.items():
            if "customer" in name.lower():
                kpis["total_customers"] = int(len(df))
                break
    return kpis


# --------------------------------------------------------------------------- #
# Trends, forecasting, correlation, anomalies
# --------------------------------------------------------------------------- #
def monthly_trend(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Aggregate revenue by month. Returns ['month', 'value'] or None."""
    rev_col, date_col = _find_col(df, REVENUE_KEYS), find_date_col(df)
    if not rev_col or not date_col:
        return None
    tmp = df[[date_col, rev_col]].copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp = tmp.dropna()
    if tmp.empty:
        return None
    out = (
        tmp.set_index(date_col)[rev_col]
        .resample("MS")
        .sum()
        .reset_index()
        .rename(columns={date_col: "month", rev_col: "value"})
    )
    return out if len(out) >= 3 else None


def linear_forecast(trend: pd.DataFrame, periods: int = 6) -> pd.DataFrame:
    """Simple linear-regression forecast over a monthly trend.

    Returns the trend extended with `periods` future months and a
    'kind' column ('actual' | 'forecast'). Intentionally simple — the
    point in an FDP demo is interpretability, not model sophistication.
    """
    y = trend["value"].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fx = np.arange(len(y), len(y) + periods, dtype=float)
    fy = np.maximum(slope * fx + intercept, 0)
    future = pd.DataFrame(
        {
            "month": pd.date_range(
                trend["month"].iloc[-1] + pd.offsets.MonthBegin(1),
                periods=periods,
                freq="MS",
            ),
            "value": fy,
            "kind": "forecast",
        }
    )
    actual = trend.assign(kind="actual")
    return pd.concat([actual, future], ignore_index=True)


def correlation_matrix(df: pd.DataFrame, max_cols: int = 12) -> Optional[pd.DataFrame]:
    """Correlation matrix of up to `max_cols` numeric columns."""
    num = df.select_dtypes(include=np.number)
    num = num.loc[:, num.nunique() > 1].iloc[:, :max_cols]
    return num.corr().round(2) if num.shape[1] >= 2 else None


def detect_anomalies(df: pd.DataFrame, z_thresh: float = 3.0) -> List[Dict[str, Any]]:
    """Z-score anomaly detection on monthly revenue."""
    trend = monthly_trend(df)
    if trend is None or len(trend) < 6:
        return []
    v = trend["value"]
    z = (v - v.mean()) / (v.std() or 1)
    return [
        {
            "month": trend["month"][i].strftime("%Y-%m"),
            "value": round(float(v[i]), 2),
            "z_score": round(float(z[i]), 2),
            "direction": "spike" if z[i] > 0 else "drop",
        }
        for i in trend.index[abs(z) >= z_thresh]
    ]


def declining_products(df: pd.DataFrame, top_n: int = 5) -> List[str]:
    """Products whose second-half revenue fell vs first half."""
    rev, prod, date = (
        _find_col(df, REVENUE_KEYS),
        _find_col(df, PRODUCT_KEYS, numeric=False),
        find_date_col(df),
    )
    if not (rev and prod and date):
        return []
    tmp = df[[date, prod, rev]].copy()
    tmp[date] = pd.to_datetime(tmp[date], errors="coerce")
    tmp = tmp.dropna()
    if tmp.empty:
        return []
    mid = tmp[date].min() + (tmp[date].max() - tmp[date].min()) / 2
    first = tmp[tmp[date] <= mid].groupby(prod)[rev].sum()
    second = tmp[tmp[date] > mid].groupby(prod)[rev].sum()
    change = ((second - first) / first.replace(0, np.nan)).dropna().sort_values()
    return [str(p) for p in change[change < -0.25].index[:top_n]]


# --------------------------------------------------------------------------- #
# Rule-based executive summary (Analytics Mode fallback)
# --------------------------------------------------------------------------- #
def rule_based_summary(
    kpis: Dict[str, Any], sheets: Dict[str, pd.DataFrame]
) -> str:
    """Deterministic executive summary — used when no LLM is available."""
    lines: List[str] = ["## 📊 Executive Summary (Rule-Based)\n"]

    rev = kpis.get("total_revenue")
    if rev is not None:
        lines.append(f"- **Total revenue:** {rev:,.0f}")
    if "total_profit" in kpis:
        lines.append(
            f"- **Total profit:** {kpis['total_profit']:,.0f} "
            f"(margin {kpis.get('profit_margin_pct', 'n/a')}%)"
        )
    if "growth_pct" in kpis:
        arrow = "📈" if kpis["growth_pct"] >= 0 else "📉"
        lines.append(f"- **Period-over-period growth:** {kpis['growth_pct']}% {arrow}")
    if "top_regions" in kpis:
        top = next(iter(kpis["top_regions"]))
        lines.append(f"- **Top region:** {top}; weakest: {kpis.get('bottom_region')}")
    if "region_margins_pct" in kpis and kpis["region_margins_pct"]:
        worst, m = next(iter(kpis["region_margins_pct"].items()))
        if m < 10:
            lines.append(
                f"- ⚠️ **Risk:** {worst} shows high revenue but a thin "
                f"{m}% margin — review pricing/logistics costs."
            )
    if "marketing_roi" in kpis:
        lines.append(f"- **Marketing ROI:** {kpis['marketing_roi']}x")
        if "channel_roi" in kpis and kpis["channel_roi"]:
            worst_ch, worst_roi = list(kpis["channel_roi"].items())[-1]
            if worst_roi < 1:
                lines.append(
                    f"- ⚠️ Channel **{worst_ch}** returns {worst_roi}x "
                    "(below break-even) — candidate for budget reallocation."
                )
    if kpis.get("items_below_reorder_point"):
        lines.append(
            f"- ⚠️ **Inventory:** {kpis['items_below_reorder_point']} SKUs below "
            "reorder point — shortage risk."
        )

    for df in sheets.values():
        anomalies = detect_anomalies(df)
        if anomalies:
            a = anomalies[0]
            lines.append(
                f"- **Anomaly:** revenue {a['direction']} in {a['month']} "
                f"(z={a['z_score']})."
            )
            break
    for df in sheets.values():
        dec = declining_products(df)
        if dec:
            lines.append(f"- **Declining products:** {', '.join(dec[:3])}")
            break

    lines.append(
        "\n*Generated by deterministic rules — configure a Groq API key "
        "for AI-narrated insights.*"
    )
    return "\n".join(lines)
