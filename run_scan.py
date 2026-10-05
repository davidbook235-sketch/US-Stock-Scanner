"""Headless run for GitHub Actions: scan -> dedup -> Telegram."""
import json, os
from datetime import date, timedelta
from pathlib import Path

from scanner import run_scan
from universe import UNIVERSE
import notifier

STATE = Path("state/sent.json")
COOLDOWN_DAYS = 5


def main():
    cfg = {
        "capital": float(os.getenv("CAPITAL", 10000)),
        "risk_pct": float(os.getenv("RISK_PCT", 1.0)),
        "min_score": int(os.getenv("MIN_SCORE", 60)),
    }
    df, regime, meta = run_scan(UNIVERSE, cfg)
    asof = meta["asof"]
    print(f"As of {asof} | regime {regime} | scanned {meta['scanned']} | signals {len(df)}")

    sent = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = date.fromisoformat(asof)
    sent = {k: v for k, v in sent.items() if date.fromisoformat(v) >= today - timedelta(days=30)}

    fresh = []
    for _, r in df.iterrows():
        key = f"{r['ticker']}|{r['setup']}"
        if key in sent and (today - date.fromisoformat(sent[key])).days < COOLDOWN_DAYS:
            continue
        fresh.append(r)
        sent[key] = asof

    if fresh:
        import pandas as pd
        ok, msg = notifier.send(notifier.format_message(pd.DataFrame(fresh), regime, asof))
        print("Telegram:", ok, msg)
    elif os.getenv("ALWAYS_NOTIFY") == "1":
        notifier.send(f"🇺🇸 US Swing Scanner {asof}: no new signals. Market {regime}.")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(sent, indent=2))


if __name__ == "__main__":
    main()
