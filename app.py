import pandas as pd
import streamlit as st

import notifier
from scanner import DEFAULT_CFG, download, run_scan
from universe import UNIVERSE

st.set_page_config(page_title="US Swing Scanner", page_icon="📈", layout="centered")
st.title("📈 US Swing Scanner")
st.caption("Daily candles • Trend + Relative Strength + Breakout/Pullback • Long only")


def creds():
    try:
        return st.secrets.get("TELEGRAM_BOT_TOKEN"), st.secrets.get("TELEGRAM_CHAT_ID")
    except Exception:
        return None, None


@st.cache_data(ttl=1800, show_spinner=False)
def cached_download(tickers: tuple):
    return download(list(tickers))


with st.expander("⚙️ Settings", expanded=False):
    c1, c2 = st.columns(2)
    capital = c1.number_input("Capital ($)", 1000.0, 10_000_000.0, 10_000.0, 500.0)
    risk_pct = c2.number_input("Risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
    min_score = st.slider("Min score", 40, 90, 60, 5)
    setups = st.multiselect("Setups", ["BREAKOUT", "PULLBACK"], ["BREAKOUT", "PULLBACK"])
    block = st.checkbox("Block new longs when SPY is bearish", True)
    extra = st.text_input("Extra tickers (comma separated)", "")

if st.button("🔍 Run Scan", type="primary", use_container_width=True):
    extra_t = [t.strip().upper() for t in extra.split(",") if t.strip()]
    tickers = sorted(set(UNIVERSE) | set(extra_t))
    with st.spinner(f"Downloading {len(tickers)} stocks..."):
        data = cached_download(tuple(sorted(set(tickers) | {"SPY"})))
    cfg = {**DEFAULT_CFG, "capital": capital, "risk_pct": risk_pct, "min_score": min_score,
           "setups": setups, "block_in_bear": block}
    df, regime, meta = run_scan(tickers, cfg, data=data)
    st.session_state.update(df=df, regime=regime, meta=meta, data=data)

if "df" in st.session_state:
    df, regime, meta, data = (st.session_state[k] for k in ("df", "regime", "meta", "data"))
    m1, m2, m3 = st.columns(3)
    m1.metric("Market (SPY)", {"BULL": "🟢 Bull", "NEUTRAL": "🟡 Neutral", "BEAR": "🔴 Bear"}[regime])
    m2.metric("Signals", len(df))
    m3.metric("As of", meta["asof"])

    if regime == "BEAR" and df.empty:
        st.warning("SPY downtrend mein hai — new long signals band hain.")
    elif df.empty:
        st.info("Abhi koi signal nahi. Min score kam karke try karo.")
    else:
        st.dataframe(df[["ticker", "setup", "score", "entry", "stop", "target1", "shares"]],
                     use_container_width=True, hide_index=True)
        for _, r in df.iterrows():
            with st.expander(f"{r['ticker']} · {r['setup']} · {r['score']}"):
                st.markdown(
                    f"**Entry** ${r['entry']}  \n**Stop** ${r['stop']} (risk ${r['risk']}/sh)  \n"
                    f"**T1** ${r['target1']} · **T2** ${r['target2']}  \n"
                    f"**Size** {r['shares']} shares  \n"
                    f"RS vs SPY +{r['rs_pct']}% · Vol x{r['vol_ratio']} · RSI {r['rsi']} · "
                    f"{r['from_52w_high_pct']}% from 52w high")
                d = data[r["ticker"]]["Close"]
                st.line_chart(pd.DataFrame({"Close": d, "SMA50": d.rolling(50).mean(),
                                            "SMA200": d.rolling(200).mean()}).tail(150))
        tok, chat = creds()
        if st.button("📨 Send to Telegram", use_container_width=True):
            ok, msg = notifier.send(notifier.format_message(df, regime, meta["asof"]), tok, chat)
            st.success("Sent ✅") if ok else st.error(msg)

st.divider()
st.caption("Educational tool, not financial advice. Always use a stop-loss.")
