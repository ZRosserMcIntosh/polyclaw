"""Discovery script - probe Polymarket APIs for trader/leaderboard data."""

import httpx
import json

SUBGRAPH_BASE = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs"
ORDERBOOK_URL = f"{SUBGRAPH_BASE}/orderbook-subgraph/0.0.1/gn"

introspect_query = '{ __schema { queryType { fields { name } } } }'


def probe_subgraphs():
    """Try to find live subgraph endpoints."""
    names = [
        "positions-subgraph/0.0.1/gn",
        "polymarket-matic-positions/prod/gn",
        "activity-subgraph/0.0.1/gn",
        "polymarket-activity/0.0.1/gn",
        "pnl-subgraph/0.0.1/gn",
        "polymarket-pnl/0.0.1/gn",
        "polymarket-matic-pnl/prod/gn",
        "open-interest-subgraph/0.0.1/gn",
    ]
    for name in names:
        url = f"{SUBGRAPH_BASE}/{name}"
        try:
            resp = httpx.post(url, json={"query": introspect_query}, timeout=10)
            if resp.status_code == 200 and "data" in resp.json():
                fields = [f["name"] for f in resp.json()["data"]["__schema"]["queryType"]["fields"]]
                print(f"  ✅ {name}")
                print(f"     Entities: {fields[:12]}")
            # else silently skip
        except Exception:
            pass


def get_top_traders():
    """Use orderbook subgraph to find most active traders."""
    # Get recent fills and aggregate by wallet
    query = """
    {
      orderFilledEvents(first: 1000, orderBy: timestamp, orderDirection: desc) {
        maker
        taker
        makerAmountFilled
        takerAmountFilled
        timestamp
      }
    }
    """
    resp = httpx.post(ORDERBOOK_URL, json={"query": query}, timeout=30)
    data = resp.json()
    fills = data.get("data", {}).get("orderFilledEvents", [])

    # Aggregate by wallet
    wallets = {}
    for fill in fills:
        for role in ["maker", "taker"]:
            addr = fill[role]
            if addr not in wallets:
                wallets[addr] = {"address": addr, "trade_count": 0, "total_volume": 0}
            wallets[addr]["trade_count"] += 1
            amount = int(fill[f"{role}AmountFilled"]) / 1e6  # USDC has 6 decimals
            wallets[addr]["total_volume"] += amount

    # Sort by trade count
    ranked = sorted(wallets.values(), key=lambda w: w["trade_count"], reverse=True)

    # Filter out known contract addresses (exchanges)
    known_contracts = {
        "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CTF Exchange
        "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # Neg Risk Exchange
    }
    ranked = [w for w in ranked if w["address"] not in known_contracts]

    print(f"\n  Found {len(ranked)} unique wallets in last 1000 fills")
    print(f"\n  Top 15 Most Active Traders:")
    print(f"  {'Rank':<5} {'Address':<44} {'Trades':<8} {'Volume (USDC)':<15}")
    print(f"  {'─'*5} {'─'*44} {'─'*8} {'─'*15}")
    for i, w in enumerate(ranked[:15], 1):
        print(f"  {i:<5} {w['address']:<44} {w['trade_count']:<8} ${w['total_volume']:>12,.2f}")

    return ranked


def check_profile_api():
    """Test if Polymarket has a profile/activity API."""
    urls = [
        "https://clob.polymarket.com/profile/0x61d0cfae8628b345690c8326525a5c63328787b8",
        "https://gamma-api.polymarket.com/activity?limit=5",
        "https://gamma-api.polymarket.com/profiles?limit=5",
    ]
    print("\n  Testing profile/activity endpoints:")
    for u in urls:
        try:
            r = httpx.get(u, timeout=10, follow_redirects=True)
            status = "✅" if r.status_code == 200 else f"❌ {r.status_code}"
            preview = r.text[:200] if r.status_code == 200 else ""
            print(f"  {status} {u}")
            if preview and preview != "null":
                print(f"       {preview}")
        except Exception as e:
            print(f"  ❌ {u}: {e}")


if __name__ == "__main__":
    print("🔍 Probing Polymarket subgraphs...")
    probe_subgraphs()

    print("\n📊 Fetching top traders from orderbook subgraph...")
    traders = get_top_traders()

    check_profile_api()

    print("\n✅ Discovery complete!")
