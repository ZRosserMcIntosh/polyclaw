"""Plotly chart generators for market data visualization."""

from __future__ import annotations

import logging
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from polyclaw.simulator.portfolio import Portfolio, PortfolioSnapshot

logger = logging.getLogger(__name__)


def equity_curve(portfolio: Portfolio, *, save_path: str | None = None) -> go.Figure:
    """Generate an equity curve chart from portfolio snapshots."""
    if not portfolio.snapshots:
        logger.warning("No snapshots to plot")
        return go.Figure()

    timestamps = [s.timestamp for s in portfolio.snapshots]
    equity = [s.total_equity for s in portfolio.snapshots]
    cash = [s.cash_balance for s in portfolio.snapshots]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Equity Curve", "Win Rate Over Time"),
        row_heights=[0.7, 0.3],
    )

    # Equity line
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=equity,
            name="Total Equity",
            line=dict(color="#00d4aa", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 212, 170, 0.1)",
        ),
        row=1, col=1,
    )

    # Starting balance reference
    fig.add_hline(
        y=portfolio.starting_balance,
        line_dash="dash",
        line_color="gray",
        annotation_text="Starting Balance",
        row=1, col=1,
    )

    # Cash balance
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=cash,
            name="Cash",
            line=dict(color="#ffa500", width=1, dash="dot"),
        ),
        row=1, col=1,
    )

    # Win rate over time
    win_rates = [s.win_rate * 100 for s in portfolio.snapshots]
    fig.add_trace(
        go.Scatter(
            x=timestamps, y=win_rates,
            name="Win Rate %",
            line=dict(color="#6c5ce7", width=2),
        ),
        row=2, col=1,
    )
    fig.add_hline(y=50, line_dash="dash", line_color="red", row=2, col=1)

    fig.update_layout(
        title="📊 PolyClaw Paper Trading Performance",
        template="plotly_dark",
        height=600,
        showlegend=True,
    )
    fig.update_yaxes(title_text="USD", row=1, col=1)
    fig.update_yaxes(title_text="Win Rate %", row=2, col=1)

    if save_path:
        fig.write_html(save_path)
        logger.info("Chart saved to %s", save_path)

    return fig


def market_spread_distribution(
    spreads: list[float],
    *,
    save_path: str | None = None,
) -> go.Figure:
    """Plot distribution of market spreads."""
    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=spreads,
            nbinsx=50,
            marker_color="#00d4aa",
            opacity=0.8,
            name="Spread Distribution",
        )
    )

    fig.update_layout(
        title="Market Bid-Ask Spread Distribution",
        xaxis_title="Spread",
        yaxis_title="Count",
        template="plotly_dark",
        height=400,
    )

    if save_path:
        fig.write_html(save_path)

    return fig


def inefficiency_timeline(
    windows: list[dict],
    *,
    save_path: str | None = None,
) -> go.Figure:
    """Plot detected inefficiency windows over time."""
    if not windows:
        return go.Figure()

    timestamps = [w["timestamp"] for w in windows]
    edges = [w["edge_pct"] for w in windows]
    symbols = [w.get("symbol", "") for w in windows]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=edges,
            mode="markers",
            marker=dict(
                size=8,
                color=edges,
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title="Edge %"),
            ),
            text=[f"{s}: {e:.1f}%" for s, e in zip(symbols, edges)],
            hoverinfo="text+x",
            name="Detected Windows",
        )
    )

    fig.update_layout(
        title="⚡ Detected Inefficiency Windows",
        xaxis_title="Time",
        yaxis_title="Edge %",
        template="plotly_dark",
        height=400,
    )

    if save_path:
        fig.write_html(save_path)

    return fig
