"""PolyClaw CLI — command-line interface for all features."""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from rich.logging import RichHandler

from polyclaw.dashboard.terminal_ui import (
    console,
    print_header,
    print_market_scan,
    print_portfolio_summary,
    print_simulation_results,
    print_wallet_profile,
    print_leaderboard,
    print_copytrade_session,
    print_kalshi_markets,
    print_exchange_comparison,
)


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(debug: bool):
    """🐾 PolyClaw — Polymarket Research & Paper Trading Platform"""
    setup_logging("DEBUG" if debug else "INFO")
    print_header()


# ---- Market Scanning -------------------------------------------------------

@main.command("scan-markets")
@click.option("--limit", default=200, help="Max markets to scan")
def scan_markets(limit: int):
    """Scan active Polymarket markets for research insights."""

    async def _run():
        from polyclaw.analysis.markets import MarketAnalyzer

        analyzer = MarketAnalyzer()
        try:
            result = await analyzer.scan_markets(limit=limit)
            print_market_scan(result)
        finally:
            await analyzer.close()

    asyncio.run(_run())


# ---- Wallet Analysis -------------------------------------------------------

@main.command("analyze-wallet")
@click.argument("address")
def analyze_wallet(address: str):
    """Analyze a Polygon wallet's on-chain trading activity."""

    async def _run():
        from polyclaw.analysis.wallets import WalletAnalyzer

        analyzer = WalletAnalyzer()
        try:
            profile = await analyzer.analyze_wallet(address)
            print_wallet_profile(profile)
        finally:
            await analyzer.close()

    asyncio.run(_run())


# ---- Inefficiency Scanner --------------------------------------------------

@main.command("scan-inefficiency")
@click.option("--duration", default=300, help="Scan duration in seconds")
@click.option("--threshold", default=3.0, help="Edge threshold in percent")
def scan_inefficiency(duration: int, threshold: float):
    """Monitor CEX vs Polymarket for latency/inefficiency windows."""

    async def _run():
        from polyclaw.analysis.inefficiency import InefficiencyScanner

        scanner = InefficiencyScanner(edge_threshold_pct=threshold)
        try:
            session = await scanner.run_scan(
                duration_seconds=duration,
                poll_interval=5.0,
            )
            console.print(f"\n[bold cyan]⚡ Scan Complete[/]")
            console.print(f"   Duration: {session.duration_seconds:.0f}s")
            console.print(f"   Ticks processed: {session.total_ticks_processed}")
            console.print(f"   Polymarket polls: {session.total_polymarket_polls}")
            console.print(f"   Windows detected: [bold]{len(session.windows_detected)}[/]")
            console.print(f"   Rate: {session.windows_per_hour:.1f}/hour")

            if session.windows_detected:
                console.print("\n[bold yellow]Detected Windows:[/]")
                for w in session.windows_detected[:20]:
                    emoji = "🟢" if w.edge_pct > 5 else "🟡"
                    console.print(
                        f"  {emoji} {w.timestamp.strftime('%H:%M:%S')} | "
                        f"{w.symbol} | Edge={w.edge_pct:.1f}% | "
                        f"PM={w.polymarket_implied_prob:.1%}→Fair={w.estimated_fair_prob:.1%}"
                    )
        finally:
            await scanner.close()

    asyncio.run(_run())


# ---- Paper Trading Simulator -----------------------------------------------

@main.command("simulate")
@click.option(
    "--strategy",
    type=click.Choice(["latency-arb", "mean-reversion", "random-baseline"]),
    default="latency-arb",
    help="Trading strategy to simulate",
)
@click.option("--balance", default=1000.0, help="Starting virtual balance (USD)")
@click.option("--duration", default=3600, help="Simulation duration in seconds")
@click.option("--poll-interval", default=10.0, help="Data polling interval (seconds)")
def simulate(strategy: str, balance: float, duration: int, poll_interval: float):
    """Run a paper trading simulation with real market data."""

    async def _run():
        from polyclaw.simulator.engine import SimulationEngine

        engine = SimulationEngine(
            strategy=strategy,
            starting_balance=balance,
        )
        try:
            results = await engine.run(
                duration_seconds=duration,
                poll_interval=poll_interval,
            )
            print_simulation_results(results)
            print_portfolio_summary(engine.portfolio)
        finally:
            await engine.stop()

    asyncio.run(_run())


# ---- Reports ---------------------------------------------------------------

@main.command("report")
@click.option("--output", default="polyclaw_report.html", help="Output file path")
def generate_report(output: str):
    """Generate an HTML report from the last simulation."""
    console.print("[yellow]Report generation requires a completed simulation.[/]")
    console.print("Run [bold]polyclaw simulate[/] first, then generate a report.")


# ---- Quick Price Check -----------------------------------------------------

@main.command("prices")
def check_prices():
    """Quick check of current BTC/ETH prices from Binance."""

    async def _run():
        from polyclaw.api.binance import BinanceClient

        client = BinanceClient()
        try:
            prices = await client.get_prices()
            console.print("\n[bold cyan]💰 Current Prices (Binance)[/]")
            for symbol, tick in prices.items():
                console.print(f"   {symbol}: [bold green]${tick.price:,.2f}[/]")
        finally:
            await client.close()

    asyncio.run(_run())


# ---- Database Init ---------------------------------------------------------

@main.command("init-db")
def init_db():
    """Initialize the SQLite database."""
    from polyclaw.data.store import DataStore

    store = DataStore()
    store.init_db()
    console.print(f"[green]✅ Database initialized at {store.db_path}[/]")


# ---- Leaderboard -----------------------------------------------------------

@main.command("leaderboard")
@click.option("--fills", default=5000, help="Number of on-chain fills to analyze")
@click.option("--top", default=30, help="Number of top traders to show")
def leaderboard(fills: int, top: int):
    """Build a ranked leaderboard of top Polymarket traders from on-chain data."""

    async def _run():
        from polyclaw.analysis.leaderboard import LeaderboardBuilder

        builder = LeaderboardBuilder(total_fills=fills, top_n=top)
        try:
            board = await builder.build()
            print_leaderboard(board)
        finally:
            await builder.close()

    asyncio.run(_run())


# ---- Copy-Trade Monitor ----------------------------------------------------

@main.command("copy-trade")
@click.argument("addresses", nargs=-1, required=True)
@click.option("--duration", default=300, help="Monitoring duration in seconds")
@click.option("--interval", default=15.0, help="Poll interval in seconds")
@click.option("--label", multiple=True, help="Labels for addresses (in order)")
def copy_trade(addresses: tuple[str, ...], duration: int, interval: float, label: tuple[str, ...]):
    """Monitor wallet(s) and paper-copy their trades in real time.

    Pass one or more wallet addresses to track. Example:

        polyclaw copy-trade 0xabc123... 0xdef456... --duration 600
    """

    async def _run():
        from polyclaw.analysis.copytrade import CopyTradeMonitor

        monitor = CopyTradeMonitor()

        for i, addr in enumerate(addresses):
            lbl = label[i] if i < len(label) else ""
            monitor.track(addr, label=lbl)

        console.print(f"\n[bold cyan]🎯 Copy-Trade Monitor[/]")
        console.print(f"   Tracking [bold]{len(addresses)}[/] wallet(s) for [bold]{duration}s[/]")
        console.print(f"   Poll interval: [bold]{interval}s[/]")
        for w in monitor.tracked_wallets:
            addr_short = f"{w.address[:8]}...{w.address[-6:]}"
            console.print(f"   → {addr_short} ({w.label})")
        console.print()

        def on_event(evt):
            addr_short = f"{evt.wallet[:6]}…{evt.wallet[-4:]}"
            console.print(
                f"   [bold green]🎯[/] {evt.timestamp.strftime('%H:%M:%S')} "
                f"| {addr_short} | {evt.role} | ${evt.amount_usd:,.2f}"
            )

        try:
            session = await monitor.run(
                duration_seconds=duration,
                poll_interval=interval,
                on_event=on_event,
            )
            print_copytrade_session(session)
        finally:
            await monitor.close()

    asyncio.run(_run())


# ---- Kalshi Markets --------------------------------------------------------

@main.command("kalshi-markets")
@click.option("--limit", default=50, help="Max markets to fetch")
@click.option("--series", default="", help="Filter by series ticker (e.g. KXBTC, KXFED)")
@click.option("--demo", is_flag=True, help="Use Kalshi demo environment")
def kalshi_markets(limit: int, series: str, demo: bool):
    """Browse active Kalshi prediction markets."""

    async def _run():
        from polyclaw.api.kalshi import KalshiClient

        client = KalshiClient(demo=demo)
        try:
            markets = await client.get_all_markets(
                status="open",
                series_ticker=series,
            )
            # Sort by volume
            markets.sort(key=lambda m: m.volume, reverse=True)
            top = markets[:limit]
            env = "demo" if demo else "production"
            print_kalshi_markets(top, title=f"Kalshi Markets ({env})")

            console.print(f"\n   Total open markets: [bold]{len(markets)}[/]")
            with_vol = [m for m in markets if m.volume > 0]
            console.print(f"   Markets with volume: [bold]{len(with_vol)}[/]")
            total_vol = sum(m.volume for m in markets)
            console.print(f"   Total volume: [bold]{total_vol:,.0f}[/] contracts")

            if client.is_authenticated:
                console.print(f"\n   [green]✅ Authenticated[/] — trading endpoints available")
            else:
                console.print(
                    f"\n   [dim]Not authenticated — set KALSHI_API_KEY_ID and "
                    f"KALSHI_PRIVATE_KEY_PATH in .env for trading[/]"
                )
        finally:
            await client.close()

    asyncio.run(_run())


@main.command("kalshi-balance")
@click.option("--demo", is_flag=True, help="Use Kalshi demo environment")
def kalshi_balance(demo: bool):
    """Check your Kalshi account balance (requires API keys)."""

    async def _run():
        from polyclaw.api.kalshi import KalshiClient

        client = KalshiClient(demo=demo)
        try:
            if not client.is_authenticated:
                console.print(
                    "[red]❌ Not authenticated.[/] Set KALSHI_API_KEY_ID and "
                    "KALSHI_PRIVATE_KEY_PATH in .env"
                )
                return

            balance = await client.get_balance()
            env = "DEMO" if demo else "PRODUCTION"
            console.print(f"\n[bold cyan]💰 Kalshi Balance ({env})[/]")
            console.print(f"   Balance: [bold green]${balance.balance:,.2f}[/]")
            console.print(f"   Payout:  [bold]${balance.payout:,.2f}[/]")

            positions = await client.get_positions()
            console.print(f"   Positions: [bold]{len(positions)}[/]")

            orders = await client.get_orders(status="resting")
            console.print(f"   Open orders: [bold]{len(orders)}[/]")
        finally:
            await client.close()

    asyncio.run(_run())


# ---- Cross-Exchange Comparison ---------------------------------------------

@main.command("compare")
@click.option("--max-markets", default=200, help="Max markets to fetch per exchange")
def compare_exchanges(max_markets: int):
    """Compare Polymarket vs Kalshi markets side by side."""

    async def _run():
        from polyclaw.analysis.compare import CrossExchangeAnalyzer

        analyzer = CrossExchangeAnalyzer()
        try:
            comp = await analyzer.compare(max_markets=max_markets)
            print_exchange_comparison(comp)
        finally:
            await analyzer.close()

    asyncio.run(_run())


# ---- Quick Leaderboard + Copy (combo) --------------------------------------

@main.command("discover-and-copy")
@click.option("--fills", default=5000, help="Fills to scan for leaderboard")
@click.option("--top", default=5, help="Top N traders to auto-track")
@click.option("--duration", default=300, help="Copy-trade monitoring duration (seconds)")
@click.option("--humans-only", is_flag=True, help="Only track likely-human traders")
def discover_and_copy(fills: int, top: int, duration: int, humans_only: bool):
    """Discover top traders, then automatically monitor and paper-copy them.

    This is the full pipeline: leaderboard → copy-trade in one command.
    """

    async def _run():
        from polyclaw.analysis.leaderboard import LeaderboardBuilder
        from polyclaw.analysis.copytrade import CopyTradeMonitor

        # Step 1: Build leaderboard
        console.print("[bold cyan]Step 1/2: Building trader leaderboard...[/]\n")
        builder = LeaderboardBuilder(total_fills=fills, top_n=top * 3)
        try:
            board = await builder.build()
            print_leaderboard(board)
        finally:
            await builder.close()

        # Step 2: Pick top traders
        candidates = board.humans_only if humans_only else board.traders
        targets = candidates[:top]

        if not targets:
            console.print("[red]No suitable traders found to copy.[/]")
            return

        console.print(f"\n[bold cyan]Step 2/2: Monitoring top {len(targets)} traders for {duration}s...[/]\n")

        monitor = CopyTradeMonitor()
        for t in targets:
            addr_short = f"{t.address[:8]}…{t.address[-6:]}"
            tier_emoji = {"whale": "🐋", "shark": "🦈", "dolphin": "🐬", "fish": "🐟"}.get(t.tier, "❓")
            monitor.track(t.address, label=f"{tier_emoji} #{t.rank} (score={t.score:.0f})")
            console.print(
                f"   → Tracking {addr_short} | {tier_emoji} {t.tier} | "
                f"Score: {t.score:.1f} | Vol: ${t.total_volume_usd:,.0f}"
            )

        console.print()

        def on_event(evt):
            addr_short = f"{evt.wallet[:6]}…{evt.wallet[-4:]}"
            console.print(
                f"   [bold green]🎯[/] {evt.timestamp.strftime('%H:%M:%S')} "
                f"| {addr_short} | {evt.role} | ${evt.amount_usd:,.2f}"
            )

        try:
            session = await monitor.run(
                duration_seconds=duration,
                poll_interval=15.0,
                on_event=on_event,
            )
            print_copytrade_session(session)
        finally:
            await monitor.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
