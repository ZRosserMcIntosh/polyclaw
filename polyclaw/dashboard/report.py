"""Report generation — HTML summary of analysis and simulation runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from polyclaw.simulator.portfolio import Portfolio
from polyclaw.dashboard.charts import equity_curve

logger = logging.getLogger(__name__)


def generate_html_report(
    portfolio: Portfolio,
    output_path: str = "polyclaw_report.html",
) -> str:
    """Generate an HTML report of paper trading results."""
    summary = portfolio.summary_dict()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Generate equity chart as embedded HTML
    fig = equity_curve(portfolio)
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn") if fig.data else ""

    trades_rows = ""
    for t in reversed(portfolio.closed_trades[-50:]):
        pnl_class = "win" if t.pnl > 0 else "loss"
        trades_rows += f"""
        <tr class="{pnl_class}">
            <td>{t.trade_id}</td>
            <td>{t.market_question[:60]}</td>
            <td>{t.side.value}</td>
            <td>${t.entry_price:.3f}</td>
            <td>${t.exit_price:.3f if t.exit_price else 'N/A'}</td>
            <td>${t.pnl:+.2f}</td>
            <td>{t.strategy}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>PolyClaw Report — {now}</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; padding: 2rem; }}
        h1 {{ color: #00d4aa; }}
        h2 {{ color: #6c5ce7; border-bottom: 1px solid #333; padding-bottom: 0.5rem; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }}
        .card {{ background: #16213e; border-radius: 8px; padding: 1rem; }}
        .card .label {{ color: #888; font-size: 0.85rem; }}
        .card .value {{ font-size: 1.4rem; font-weight: bold; margin-top: 0.3rem; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th {{ background: #16213e; padding: 0.7rem; text-align: left; }}
        td {{ padding: 0.5rem 0.7rem; border-bottom: 1px solid #222; }}
        .win td:nth-child(6) {{ color: #00d4aa; }}
        .loss td:nth-child(6) {{ color: #ff6b6b; }}
        .disclaimer {{ background: #2d1b00; border: 1px solid #ff9500; border-radius: 8px; padding: 1rem; margin: 2rem 0; }}
    </style>
</head>
<body>
    <h1>🐾 PolyClaw Paper Trading Report</h1>
    <p>Generated: {now}</p>

    <div class="disclaimer">
        ⚠️ <strong>Disclaimer:</strong> This is a paper trading simulation.
        No real money was used. Past simulated performance does not predict future results.
    </div>

    <h2>Portfolio Summary</h2>
    <div class="summary">
        {"".join(f'<div class="card"><div class="label">{k}</div><div class="value">{v}</div></div>' for k, v in summary.items())}
    </div>

    <h2>Equity Curve</h2>
    {chart_html}

    <h2>Trade History (last 50)</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Market</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Strategy</th></tr>
        </thead>
        <tbody>
            {trades_rows}
        </tbody>
    </table>

    <p style="color: #666; margin-top: 2rem;">
        PolyClaw v0.1.0 — Research & Education Only
    </p>
</body>
</html>"""

    Path(output_path).write_text(html)
    logger.info("Report saved to %s", output_path)
    return output_path
