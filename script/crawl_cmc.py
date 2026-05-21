"""
CoinMarketCap Daily Crawler
=============================
- Top 1500 coin: rank, name, symbol, price, 24h%, 7d%, market cap, volume, supply
- Top 500 detail: FDV, Liq/Mkt Cap%, Vol/Mkt Cap%
- Daily snapshot CSV  +  master_daily.csv  +  Google Sheets
- Chạy 7:00 AM Vietnam (00:00 UTC) qua GitHub Actions
"""

import requests
import pandas as pd
import time
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Google Sheets ──────────────────────────────────────────────
import gspread
from google.oauth2.service_account import Credentials

# ── Logging ────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/crawl.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────
CMC_BASE = "https://coinmarketcap.com"

# Headers giống browser thật — quan trọng để không bị block
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://coinmarketcap.com",
    "Referer": "https://coinmarketcap.com/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

DELAY_BETWEEN_PAGES  = 3    # giây delay giữa trang listing
DELAY_BETWEEN_DETAIL = 1.5  # giây delay giữa detail từng coin

# Timezone VN UTC+7
VN_TZ = timezone(timedelta(hours=7))
TODAY = datetime.now(VN_TZ).strftime("%Y-%m-%d")

# ── Paths ──────────────────────────────────────────────────────
DATA_DIR      = Path("data");  DATA_DIR.mkdir(exist_ok=True)
SNAPSHOT_PATH = DATA_DIR / f"snapshot_{TODAY}.csv"
MASTER_PATH   = DATA_DIR / "master_daily.csv"


# ══════════════════════════════════════════════════════════════
#  STEP 1 — Crawl danh sách coin (internal API)
# ══════════════════════════════════════════════════════════════
def fetch_listing_page(start: int, limit: int, session: requests.Session) -> list[dict]:
    """
    Dùng CMC internal data API (public, không cần API key).
    Endpoint: /data-api/v3/cryptocurrency/listing
    """
    url = (
        "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing"
        f"?start={start}&limit={limit}"
        "&sortBy=market_cap&sortType=desc"
        "&convert=USD&cryptoType=all&tagType=all&audited=false"
        "&aux=ath,atl,high24h,low24h,num_market_pairs,cmc_rank,"
        "date_added,max_supply,circulating_supply,total_supply"
    )
    log.info(f"  → Listing API: start={start}, limit={limit}")
    r = session.get(url, timeout=30)
    r.raise_for_status()
    raw = r.json()

    coins = []
    for item in raw.get("data", {}).get("cryptoCurrencyList", []):
        # Lấy USD quote
        quotes = item.get("quotes", [])
        q = next((x for x in quotes if x.get("name") == "USD"), quotes[0] if quotes else {})

        coins.append({
            "rank":               item.get("cmcRank"),
            "name":               item.get("name"),
            "symbol":             item.get("symbol"),
            "slug":               item.get("slug"),
            "price_usd":          q.get("price"),
            "change_1h_pct":      q.get("percentChange1h"),
            "change_24h_pct":     q.get("percentChange24h"),
            "change_7d_pct":      q.get("percentChange7d"),
            "market_cap_usd":     q.get("marketCap"),
            "volume_24h_usd":     q.get("volume24h"),
            "circulating_supply": item.get("circulatingSupply"),
            "total_supply":       item.get("totalSupply"),
            "max_supply":         item.get("maxSupply"),
            "date_snapshot":      TODAY,
        })
    return coins


def crawl_listing(total: int = 1500) -> pd.DataFrame:
    """Crawl listing cho `total` coin đầu theo market cap."""
    session = requests.Session()
    session.headers.update(HEADERS)

    all_coins: list[dict] = []
    start = 1
    batch = 200  # 200 coins/request — ổn định hơn 500

    while len(all_coins) < total:
        remaining = total - len(all_coins)
        limit = min(batch, remaining)
        try:
            coins = fetch_listing_page(start, limit, session)
        except Exception as e:
            log.error(f"  Listing fetch failed at start={start}: {e}")
            break

        if not coins:
            log.warning("  No more coins returned — stopping.")
            break

        all_coins.extend(coins)
        log.info(f"  Fetched {len(all_coins)}/{total} coins so far ...")
        start += len(coins)

        if len(all_coins) < total:
            time.sleep(DELAY_BETWEEN_PAGES)

    df = pd.DataFrame(all_coins)
    log.info(f"Listing done — {len(df)} coins.")
    return df


# ══════════════════════════════════════════════════════════════
#  STEP 2 — Detail từng coin (FDV, Liq/Mkt Cap, Vol/Mkt Cap)
# ══════════════════════════════════════════════════════════════
def fetch_coin_detail(slug: str, session: requests.Session) -> dict:
    """
    Dùng CMC detail API để lấy FDV và các metric bổ sung.
    """
    url = (
        "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail"
        f"?slug={slug}"
        "&aux=urls,logo,description,tags,platform,date_added,notice,status"
    )
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        d = r.json().get("data", {})
        stats = d.get("statistics", {})

        fdv        = stats.get("fullyDilutedMarketCap")
        market_cap = stats.get("marketCap")
        volume_24h = stats.get("volume24h")

        # Liq/Mkt Cap = Volume24h / MarketCap * 100
        liq_mkt = (volume_24h / market_cap * 100) if (market_cap and volume_24h and market_cap > 0) else None

        return {
            "fdv_usd":            fdv,
            "liq_mkt_cap_pct":    round(liq_mkt, 4) if liq_mkt is not None else None,
        }
    except Exception as e:
        log.warning(f"    Detail failed [{slug}]: {e}")
        return {"fdv_usd": None, "liq_mkt_cap_pct": None}


def enrich_with_details(df: pd.DataFrame, max_coins: int = 500) -> pd.DataFrame:
    """Enrich top `max_coins` với FDV và Liq/Mkt Cap từ detail API."""
    df["fdv_usd"]         = None
    df["liq_mkt_cap_pct"] = None

    session = requests.Session()
    session.headers.update(HEADERS)

    top = df[df["rank"] <= max_coins]
    log.info(f"Enriching {len(top)} coins with detail data ...")

    for i, (idx, row) in enumerate(top.iterrows(), 1):
        log.info(f"  [{i:>3}/{len(top)}] {row['name']:25s} ({row['slug']})")
        detail = fetch_coin_detail(row["slug"], session)
        df.at[idx, "fdv_usd"]         = detail["fdv_usd"]
        df.at[idx, "liq_mkt_cap_pct"] = detail["liq_mkt_cap_pct"]
        time.sleep(DELAY_BETWEEN_DETAIL)

    log.info("Detail enrichment done.")
    return df


# ══════════════════════════════════════════════════════════════
#  STEP 3 — Save CSV
# ══════════════════════════════════════════════════════════════
def save_csv(df: pd.DataFrame):
    # Snapshot ngày hôm nay
    df.to_csv(SNAPSHOT_PATH, index=False, encoding="utf-8-sig")
    log.info(f"Snapshot → {SNAPSHOT_PATH}")

    # Append vào master (historical)
    if MASTER_PATH.exists():
        master = pd.read_csv(MASTER_PATH, low_memory=False)
        master = master[master["date_snapshot"] != TODAY]  # idempotent
        master = pd.concat([master, df], ignore_index=True)
    else:
        master = df.copy()

    master.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")
    log.info(f"Master   → {MASTER_PATH}  ({len(master)} total rows)")


# ══════════════════════════════════════════════════════════════
#  STEP 4 — Push to Google Sheets
# ══════════════════════════════════════════════════════════════
def push_to_sheets(df: pd.DataFrame, spreadsheet_id: str):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        log.warning("GOOGLE_CREDENTIALS_JSON not set — skip Sheets.")
        return

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    gc    = gspread.authorize(creds)
    ss    = gc.open_by_key(spreadsheet_id)

    # Helper: format DataFrame thành list-of-lists cho gspread
    def df_to_rows(d: pd.DataFrame) -> list:
        return [d.columns.tolist()] + d.fillna("").astype(str).values.tolist()

    # ── Sheet 1: Daily Snapshot (overwrite mỗi ngày) ──────────
    try:
        ws = ss.worksheet("Daily Snapshot")
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet("Daily Snapshot", rows=2000, cols=25)
    ws.update(df_to_rows(df), value_input_option="USER_ENTERED")
    log.info(f"Sheets 'Daily Snapshot' updated — {len(df)} rows")

    # ── Sheet 2: Master (append, idempotent) ──────────────────
    try:
        ws_m = ss.worksheet("Master")
        existing = ws_m.get_all_values()
        if len(existing) <= 1:
            ws_m.update(df_to_rows(df), value_input_option="USER_ENTERED")
        else:
            header = existing[0]
            if "date_snapshot" in header:
                di = header.index("date_snapshot")
                kept = [r for r in existing[1:] if r[di] != TODAY]
            else:
                kept = existing[1:]
            new_rows = [header] + kept + df.fillna("").astype(str).values.tolist()
            ws_m.clear()
            ws_m.update(new_rows, value_input_option="USER_ENTERED")
    except gspread.WorksheetNotFound:
        ws_m = ss.add_worksheet("Master", rows=60000, cols=25)
        ws_m.update(df_to_rows(df), value_input_option="USER_ENTERED")

    log.info("Sheets 'Master' updated.")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
def main():
    log.info("=" * 60)
    log.info(f"CMC Crawler  |  {TODAY}  |  Vietnam 7h sáng")
    log.info("=" * 60)

    # 1) Listing 1500 coin
    df = crawl_listing(total=1500)

    # 2) Detail top 500
    df = enrich_with_details(df, max_coins=500)

    # 3) Sort + clean
    df = df.sort_values("rank").reset_index(drop=True)

    # 4) Save CSV
    save_csv(df)

    # 5) Google Sheets
    sid = os.environ.get("GOOGLE_SPREADSHEET_ID", "")
    if sid:
        push_to_sheets(df, sid)
    else:
        log.warning("GOOGLE_SPREADSHEET_ID not set — skip Sheets.")

    log.info("✅  Done!")


if __name__ == "__main__":
    main()
