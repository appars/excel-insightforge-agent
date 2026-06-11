"""
Visualization service — all Plotly figure builders in one place.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from services import analytics

TEMPLATE = "plotly_white"
HEIGHT = 420


def bar_top(df: pd.DataFrame, group_col: str, value_col: str, title: str) -> go.Figure:
    data = (
        df.groupby(group_col)[value_col]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )
    fig = px.bar(
        data, x=group_col, y=value_col, title=title,
        color=value_col, color_continuous_scale="Teal",
    )
    fig.update_layout(template=TEMPLATE, height=HEIGHT, coloraxis_showscale=False)
    return fig


def pie_share(df: pd.DataFrame, group_col: str, value_col: str, title: str) -> go.Figure:
    data = df.groupby(group_col)[value_col].sum().reset_index()
    fig = px.pie(data, names=group_col, values=value_col, title=title, hole=0.35)
    fig.update_layout(template=TEMPLATE, height=HEIGHT)
    return fig


def line_trend(trend: pd.DataFrame, title: str) -> go.Figure:
    fig = px.line(trend, x="month", y="value", markers=True, title=title)
    fig.update_layout(
        template=TEMPLATE, height=HEIGHT,
        xaxis_title="Month", yaxis_title="Revenue",
    )
    return fig


def forecast_chart(df: pd.DataFrame, title: str) -> Optional[go.Figure]:
    trend = analytics.monthly_trend(df)
    if trend is None:
        return None
    data = analytics.linear_forecast(trend)
    fig = go.Figure()
    for kind, dash, color in (("actual", None, "#0f766e"), ("forecast", "dash", "#f59e0b")):
        seg = data[data["kind"] == kind]
        fig.add_trace(
            go.Scatter(
                x=seg["month"], y=seg["value"], name=kind.title(),
                mode="lines+markers", line=dict(dash=dash, color=color),
            )
        )
    fig.update_layout(
        template=TEMPLATE, height=HEIGHT, title=title,
        xaxis_title="Month", yaxis_title="Revenue",
    )
    return fig


def correlation_heatmap(df: pd.DataFrame, title: str) -> Optional[go.Figure]:
    corr = analytics.correlation_matrix(df)
    if corr is None:
        return None
    fig = px.imshow(
        corr, text_auto=True, title=title,
        color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto",
    )
    fig.update_layout(template=TEMPLATE, height=HEIGHT + 60)
    return fig
