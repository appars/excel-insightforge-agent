"""
Demo dataset generator — "Global E-Commerce Analytics".

Generates a realistic multi-sheet workbook with DELIBERATELY embedded
business stories so the AI summary always has something to find:

* Middle East: high revenue, razor-thin margins (heavy logistics cost)
* November/December seasonal spikes; one anomalous flash-sale month
* 'Cassette Adapter' & 'DVD Combo Pack' products in steady decline
* Marketing: 'Print Ads' channel with ROI < 1
* Supply chain: ~8% of SKUs below reorder point, one bottleneck supplier
"""

from __future__ import annotations

import io
import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger("insightforge.datagen")

RNG_SEED = 42

REGIONS = {
    "North America": {"weight": 0.30, "margin": 0.22},
    "Europe": {"weight": 0.25, "margin": 0.18},
    "Asia Pacific": {"weight": 0.20, "margin": 0.15},
    "Middle East": {"weight": 0.15, "margin": 0.04},   # high rev, low profit
    "Latin America": {"weight": 0.10, "margin": 0.12},
}
CATEGORIES = ["Electronics", "Fashion", "Home & Garden", "Sports", "Beauty"]
CHANNELS = ["Social Media", "Search Ads", "Email", "Influencer", "Print Ads"]
DECLINING = ["Cassette Adapter", "DVD Combo Pack"]


def generate_workbook(
    n_orders: int = 50_000,
    n_customers: int = 10_000,
    n_products: int = 500,
    seed: int = RNG_SEED,
) -> Dict[str, pd.DataFrame]:
    """Generate all five sheets and return them as a dict of DataFrames."""
    rng = np.random.default_rng(seed)
    logger.info("Generating demo dataset: %s orders", n_orders)

    # ---------------- Products ----------------
    prod_ids = np.arange(1, n_products + 1)
    prod_names = [f"{rng.choice(CATEGORIES)[:4]}-Item-{i:04d}" for i in prod_ids]
    # Plant the declining products at fixed slots
    prod_names[0], prod_names[1] = DECLINING[0], DECLINING[1]
    base_price = np.round(rng.uniform(8, 900, n_products), 2)
    products = pd.DataFrame(
        {
            "product_id": prod_ids,
            "product_name": prod_names,
            "category": rng.choice(CATEGORIES, n_products),
            "unit_price": base_price,
            "unit_cost": np.round(base_price * rng.uniform(0.45, 0.8, n_products), 2),
            "rating": np.round(rng.uniform(2.5, 5.0, n_products), 1),
        }
    )

    # ---------------- Customers ----------------
    region_names = list(REGIONS)
    region_w = [REGIONS[r]["weight"] for r in region_names]
    customers = pd.DataFrame(
        {
            "customer_id": np.arange(1, n_customers + 1),
            "region": rng.choice(region_names, n_customers, p=region_w),
            "segment": rng.choice(
                ["Consumer", "Corporate", "Small Business"], n_customers,
                p=[0.6, 0.25, 0.15],
            ),
            "signup_date": pd.to_datetime("2024-01-01")
            + pd.to_timedelta(rng.integers(0, 720, n_customers), unit="D"),
            "lifetime_orders": rng.poisson(5, n_customers),
        }
    )

    # ---------------- Orders ----------------
    dates = pd.date_range("2024-06-01", "2026-05-31", freq="D")
    month_boost = np.where(np.isin(dates.month, [11, 12]), 2.2, 1.0)  # seasonality
    month_boost = month_boost * np.where(  # anomalous flash-sale month
        (dates.year == 2025) & (dates.month == 7), 3.5, 1.0
    )
    date_p = month_boost / month_boost.sum()
    order_dates = rng.choice(dates, n_orders, p=date_p)

    cust_idx = rng.integers(0, n_customers, n_orders)
    order_regions = customers["region"].to_numpy()[cust_idx]

    # Product mix: declining products fade over time
    prod_idx = rng.integers(0, n_products, n_orders)
    t_frac = (
        pd.to_datetime(order_dates) - dates[0]
    ).days.to_numpy() / max((dates[-1] - dates[0]).days, 1)
    is_declining = prod_idx < 2
    keep = ~(is_declining & (rng.random(n_orders) < t_frac * 0.9))
    prod_idx = np.where(keep, prod_idx, rng.integers(2, n_products, n_orders))

    qty = rng.integers(1, 6, n_orders)
    price = products["unit_price"].to_numpy()[prod_idx]
    cost = products["unit_cost"].to_numpy()[prod_idx]
    revenue = np.round(price * qty * rng.uniform(0.92, 1.0, n_orders), 2)

    margin_map = {r: REGIONS[r]["margin"] for r in REGIONS}
    region_margin = np.vectorize(margin_map.get)(order_regions)
    base_profit = revenue - cost * qty
    profit = np.round(
        np.minimum(base_profit, revenue * region_margin)
        * rng.uniform(0.85, 1.1, n_orders),
        2,
    )

    orders = pd.DataFrame(
        {
            "order_id": np.arange(1, n_orders + 1),
            "order_date": pd.to_datetime(order_dates),
            "customer_id": customers["customer_id"].to_numpy()[cust_idx],
            "region": order_regions,
            "product_id": products["product_id"].to_numpy()[prod_idx],
            "product_name": products["product_name"].to_numpy()[prod_idx],
            "category": products["category"].to_numpy()[prod_idx],
            "quantity": qty,
            "revenue": revenue,
            "profit": profit,
        }
    ).sort_values("order_date", ignore_index=True)

    # ---------------- Marketing ----------------
    months = pd.date_range("2024-06-01", "2026-05-01", freq="MS")
    rows = []
    for m in months:
        for ch in CHANNELS:
            spend = float(rng.uniform(20_000, 90_000))
            roi = {"Print Ads": 0.65}.get(ch, float(rng.uniform(1.4, 4.2)))
            rows.append(
                {
                    "month": m,
                    "channel": ch,
                    "spend": round(spend, 2),
                    "attributed_revenue": round(spend * roi * rng.uniform(0.9, 1.1), 2),
                    "impressions": int(spend * rng.uniform(8, 25)),
                    "clicks": int(spend * rng.uniform(0.4, 1.2)),
                }
            )
    marketing = pd.DataFrame(rows)

    # ---------------- Supply chain ----------------
    suppliers = [f"Supplier-{c}" for c in "ABCDEFGH"]
    stock = rng.integers(0, 800, n_products)
    reorder = rng.integers(50, 200, n_products)
    short_mask = rng.random(n_products) < 0.08  # planted shortages
    stock = np.where(short_mask, rng.integers(0, 40, n_products), stock)
    sup = rng.choice(suppliers, n_products)
    lead = rng.integers(3, 15, n_products)
    lead = np.where(sup == "Supplier-F", rng.integers(25, 45, n_products), lead)

    supply = pd.DataFrame(
        {
            "product_id": prod_ids,
            "product_name": products["product_name"],
            "supplier": sup,
            "stock_on_hand": stock,
            "reorder_point": reorder,
            "lead_time_days": lead,
            "warehouse": rng.choice(["US-East", "EU-Central", "APAC-1"], n_products),
        }
    )

    return {
        "Orders": orders,
        "Customers": customers,
        "Products": products,
        "Marketing": marketing,
        "SupplyChain": supply,
    }


def workbook_to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    """Serialize the workbook to .xlsx bytes for download."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()
