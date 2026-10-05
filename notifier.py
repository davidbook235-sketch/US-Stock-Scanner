"""Telegram helper."""
import os
import requests

EMOJI = {"BULL": "🟢", "NEUTRAL": "🟡", "BEAR": "🔴"}


def send(text: str, token: str | None = None, chat_id: str | None = None):
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram token/chat id missing"
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)]
    for ch in chunks:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat_id, "text": ch, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        if r.status_code != 200:
            return False, r.text
    return True, "sent"


def format_message(df, regime: str, asof: str, max_n: int = 8) -> str:
    lines = [f"<b>🇺🇸 US Swing Scanner</b> — {asof}",
             f"Market (SPY): {EMOJI.get(regime, '')} {regime} | Signals: {len(df)}", ""]
    for _, r in df.head(max_n).iterrows():
        lines.append(
            f"<b>{r['ticker']}</b> · {r['setup']} · Score {r['score']}\n"
            f"Entry ${r['entry']} | SL ${r['stop']}\n"
            f"T1 ${r['target1']} | T2 ${r['target2']}\n"
            f"Risk/share ${r['risk']} · Size {r['shares']} sh\n"
            f"RS +{r['rs_pct']}% · Vol x{r['vol_ratio']} · RSI {r['rsi']}\n")
    lines.append("⚠️ Educational use only. Not financial advice.")
    return "\n".join(lines)
