"""Rich terminal UI for live monitoring and dashboards."""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from polyclaw.analysis.markets import MarketScanResult
from polyclaw.analysis.wallets import WalletProfile
from polyclaw.simulator.portfolio import Portfolio

logger = logging.getLogger(__name__)
console = Console()


def print_header():
    """Print the PolyClaw banner."""
    banner = Text()
    banner.append("🐾 ", style="bold")
    banner.append("PolyClaw", style="bold cyan")
    banner.append(" — Polymarket Research & Paper Trading Platform\n", style="dim")
    banner.append("   Educational tool • No real money • No financial advice", style="dim yellow")
    console.print(Panel(banner, box=box.DOUBLE))


def print_market_scan(result: MarketScanResult):
    """Display market scan results in formatted tables."""
    console.print()
    console.print(f"[bold cyan]📊 Market Scan Results[/]")
    console.print(f"   Markets scanned: [bold]{result.total_markets}[/]")
    console.print(f"   Total volume: [bold green]${result.total_volume:,.0f}[/]")
    console.print(f"   Average spread: [bold]{result.avg_spread:.4f}[/]")
    console.print()

    # Highest volume markets
    if result.highest_volume:
        table = Table(
            title="🔥 Highest Volume Markets (24h)",
            box=box.SIMPLE_HEAVY,
            show_lines=True,
        )
        table.add_column("Question", style="white", max_width=50)
        table.add_column("24h Vol", style="green", justify="right")
        table.add_column("Liquidity", style="cyan", justify="right")
        table.add_column("Bid/Ask", justify="center")
        table.add_column("Spread", style="yellow", justify="right")

        for m in result.highest_volume[:10]:
            table.add_row(
                m["question"],
                f"${m['volume_24h']:,.0f}",
                f"${m['liquidity']:,.0f}",
                f"{m['best_bid']:.3f}/{m['best_ask']:.3f}",
                f"{m['spread']:.4f}",
            )
        console.print(table)
        console.print()

    # Widest spreads (potential inefficiency)
    if result.widest_spreads:
        table = Table(
            title="📏 Widest Spreads (Potential Inefficiency)",
            box=box.SIMPLE_HEAVY,
            show_lines=True,
        )
        table.add_column("Question", style="white", max_width=50)
        table.add_column("Spread", style="red bold", justify="right")
        table.add_column("Bid", style="green", justify="right")
        table.add_column("Ask", style="red", justify="right")
        table.add_column("Volume", justify="right")

        for m in result.widest_spreads[:10]:
            table.add_row(
                m["question"],
                f"{m['spread']:.4f}",
                f"{m['best_bid']:.3f}",
                f"{m['best_ask']:.3f}",
                f"${m['volume']:,.0f}",
            )
        console.print(table)
        console.print()

    # Crypto markets
    if result.crypto_markets:
        table = Table(
            title="₿ Crypto Markets",
            box=box.SIMPLE_HEAVY,
            show_lines=True,
        )
        table.add_column("Question", style="white", max_width=60)
        table.add_column("24h Vol", style="green", justify="right")
        table.add_column("Last Price", style="cyan", justify="right")
        table.add_column("Spread", style="yellow", justify="right")

        for m in result.crypto_markets[:10]:
            table.add_row(
                m["question"],
                f"${m['volume_24h']:,.0f}",
                f"{m['last_price']:.3f}",
                f"{m['spread']:.4f}",
            )
        console.print(table)


def print_wallet_profile(profile: WalletProfile):
    """Display wallet analysis results."""
    console.print()
    addr_short = f"{profile.address[:8]}...{profile.address[-6:]}"

    table = Table(
        title=f"🔍 Wallet Analysis: {addr_short}",
        box=box.DOUBLE,
        show_lines=True,
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    if profile.summary:
        table.add_row("Total Transactions", str(profile.summary.total_transactions))
        table.add_row("Token Transfers", str(profile.summary.total_token_transfers))
        table.add_row(
            "First Seen",
            profile.summary.first_seen.strftime("%Y-%m-%d") if profile.summary.first_seen else "N/A",
        )
        table.add_row(
            "Last Seen",
            profile.summary.last_seen.strftime("%Y-%m-%d") if profile.summary.last_seen else "N/A",
        )
        table.add_row("Contracts Interacted", str(profile.summary.unique_contracts_interacted))

    table.add_row("Est. Polymarket Trades", str(profile.estimated_trade_count))
    table.add_row("Activity Days", str(profile.activity_days))
    table.add_row("Avg Trades/Day", f"{profile.avg_trades_per_day:.1f}")

    # Bot detection
    bot_status = "🤖 Likely Bot" if profile.is_likely_bot else "👤 Likely Human"
    bot_color = "red" if profile.is_likely_bot else "green"
    table.add_row("Bot Detection", f"[{bot_color}]{bot_status}[/] ({profile.bot_confidence:.0%})")

    console.print(table)

    if profile.bot_signals:
        console.print("\n[bold yellow]Bot Signals:[/]")
        for signal in profile.bot_signals:
            console.print(f"  ⚡ {signal}")


def print_portfolio_summary(portfolio: Portfolio):
    """Display paper trading portfolio summary."""
    console.print()
    summary = portfolio.summary_dict()

    table = Table(
        title="💼 Paper Portfolio",
        box=box.DOUBLE,
        show_lines=True,
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    for key, value in summary.items():
        style = ""
        if "PnL" in key or "Return" in key:
            if value.startswith("-") or value.startswith("$-"):
                style = "red"
            elif value.startswith("+") or (value.startswith("$") and not value.startswith("$-")):
                style = "green"
        table.add_row(key, f"[{style}]{value}[/]" if style else value)

    console.print(table)

    # Recent trades
    recent = portfolio.closed_trades[-10:]
    if recent:
        trades_table = Table(
            title="📝 Recent Trades",
            box=box.SIMPLE,
        )
        trades_table.add_column("#", justify="right")
        trades_table.add_column("Market", max_width=40)
        trades_table.add_column("Side", justify="center")
        trades_table.add_column("Entry", justify="right")
        trades_table.add_column("Exit", justify="right")
        trades_table.add_column("PnL", justify="right")
        trades_table.add_column("Strategy")

        for t in reversed(recent):
            pnl_style = "green" if t.pnl > 0 else "red"
            trades_table.add_row(
                str(t.trade_id),
                t.market_question[:40],
                t.side.value,
                f"${t.entry_price:.3f}",
                f"${t.exit_price:.3f}" if t.exit_price is not None else "—",
                f"[{pnl_style}]${t.pnl:+.2f}[/]",
                t.strategy,
            )
        console.print(trades_table)


def print_simulation_results(results: dict[str, Any]):
    """Display paper trading simulation results."""
    console.print()
    console.print("[bold cyan]🧪 Simulation Results[/]")
    console.print()

    table = Table(box=box.DOUBLE, show_lines=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    for key, value in results.items():
        if key == "Risk Status":
            continue
        if isinstance(value, dict):
            value = str(value)
        table.add_row(str(key), str(value))

    console.print(table)

    # Risk status
    risk = results.get("Risk Status", {})
    if risk:
        risk_table = Table(title="🛡️ Risk Status", box=box.SIMPLE)
        risk_table.add_column("Check", style="cyan")
        risk_table.add_column("Status", style="white")
        for k, v in risk.items():
            table.add_row(str(k), str(v))
        console.print(risk_table)


def print_leaderboard(board):
    """Display the trader leaderboard."""
    from polyclaw.analysis.leaderboard import EnrichedLeaderboard

    lb: EnrichedLeaderboard = board

    console.print()
    console.print("[bold cyan]🏆 PolyClaw Trader Leaderboard[/]")
    console.print(
        f"   Fills analyzed: [bold]{lb.total_fills_analyzed:,}[/]  |  "
        f"Unique wallets: [bold]{lb.total_unique_wallets:,}[/]  |  "
        f"Window: [bold]{lb.time_window_hours:.1f}h[/]  |  "
        f"Scan time: [bold]{lb.scan_duration_seconds:.1f}s[/]"
    )
    console.print()

    # Tier emoji map
    tier_emoji = {"whale": "🐋", "shark": "🦈", "dolphin": "🐬", "fish": "🐟"}

    table = Table(
        title="Top Traders by Composite Score",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Tier", justify="center", width=4)
    table.add_column("Address", style="cyan", width=16)
    table.add_column("Score", style="bold yellow", justify="right", width=7)
    table.add_column("Volume", style="green", justify="right", width=12)
    table.add_column("Trades", justify="right", width=7)
    table.add_column("Avg Size", justify="right", width=10)
    table.add_column("Maker%", justify="right", width=7)
    table.add_column("Trades/Day", justify="right", width=10)
    table.add_column("Type", justify="center", width=6)

    for t in lb.traders[:30]:
        emoji = tier_emoji.get(t.tier, "❓")
        addr_short = f"{t.address[:6]}…{t.address[-4:]}"
        bot_label = "🤖" if t.is_likely_bot else "👤"

        table.add_row(
            str(t.rank),
            emoji,
            addr_short,
            f"{t.score:.1f}",
            f"${t.total_volume_usd:,.0f}",
            str(t.trade_count),
            f"${t.avg_trade_size:,.0f}",
            f"{t.maker_ratio:.0%}",
            f"{t.trades_per_day:.1f}",
            bot_label,
        )

    console.print(table)

    # Summary row
    humans = lb.humans_only
    bots = [t for t in lb.traders if t.is_likely_bot]
    console.print(
        f"\n   👤 Humans: [bold]{len(humans)}[/]  |  "
        f"🤖 Likely Bots: [bold]{len(bots)}[/]  |  "
        f"🐋 Whales: [bold]{len(lb.whales)}[/]  |  "
        f"🦈 Sharks: [bold]{len(lb.sharks)}[/]"
    )
    console.print()


def print_copytrade_session(session):
    """Display copy-trade monitoring session results."""
    from polyclaw.analysis.copytrade import CopyTradeSession

    s: CopyTradeSession = session

    console.print()
    console.print("[bold cyan]🎯 Copy-Trade Monitor Session[/]")
    console.print(
        f"   Duration: [bold]{s.duration_seconds:.0f}s[/]  |  "
        f"Polls: [bold]{s.total_polls}[/]  |  "
        f"Wallets tracked: [bold]{s.wallets_tracked}[/]  |  "
        f"Events detected: [bold]{s.total_events}[/]"
    )

    if not s.events:
        console.print(
            "\n   [dim]No trades detected from tracked wallets during this session.[/]"
        )
        console.print(
            "   [dim]This is normal — wallets may not trade during short windows.[/]"
        )
        return

    console.print()

    table = Table(
        title="Detected Copy-Trade Events",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )
    table.add_column("Time", style="dim", width=10)
    table.add_column("Wallet", style="cyan", width=16)
    table.add_column("Role", justify="center", width=7)
    table.add_column("Amount", style="green", justify="right", width=12)
    table.add_column("Counterparty", style="dim", width=16)
    table.add_column("Copied?", justify="center", width=7)

    for evt in s.events[:50]:
        addr_short = f"{evt.wallet[:6]}…{evt.wallet[-4:]}"
        cp_short = f"{evt.counterparty[:6]}…{evt.counterparty[-4:]}"
        role_color = "green" if evt.role == "maker" else "yellow"
        copied = "✅" if evt.paper_copied else "❌"

        table.add_row(
            evt.timestamp.strftime("%H:%M:%S"),
            addr_short,
            f"[{role_color}]{evt.role}[/]",
            f"${evt.amount_usd:,.2f}",
            cp_short,
            copied,
        )

    console.print(table)

    # Per-wallet summary
    wallet_volumes: dict[str, float] = {}
    wallet_counts: dict[str, int] = {}
    for evt in s.events:
        wallet_volumes[evt.wallet] = wallet_volumes.get(evt.wallet, 0) + evt.amount_usd
        wallet_counts[evt.wallet] = wallet_counts.get(evt.wallet, 0) + 1

    console.print("\n[bold]Per-Wallet Summary:[/]")
    for addr, vol in sorted(wallet_volumes.items(), key=lambda x: -x[1]):
        addr_short = f"{addr[:6]}…{addr[-4:]}"
        console.print(
            f"   {addr_short}: {wallet_counts[addr]} events, ${vol:,.2f} volume"
        )
