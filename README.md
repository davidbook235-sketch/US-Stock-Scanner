# US Swing Scanner (GitHub + Streamlit + Telegram)

## Mobile setup
1. Telegram: @BotFather -> /newbot -> BOT TOKEN. Bot ko ek message bhejo, phir @userinfobot se apna CHAT ID lo.
2. GitHub: new repo banao, saari files upload karo (Add file -> Upload files).
   `.github/workflows/scan.yml` ko "Add file -> Create new file" mein naam `.github/workflows/scan.yml` likh kar paste karo.
3. Repo -> Settings -> Secrets and variables -> Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` add karo.
4. Actions tab -> "US Swing Scan" -> Run workflow (test). Roz US close ke baad auto chalega.
5. Streamlit: share.streamlit.io -> New app -> repo + `app.py`. Advanced settings -> Secrets:
   TELEGRAM_BOT_TOKEN = "xxx"
   TELEGRAM_CHAT_ID = "123456"

## Logic
Liquidity ($20M+/day, price $10+) -> Uptrend (Close > SMA50 > SMA200, SMA50 rising) -> RS vs SPY (63d) ->
BREAKOUT (20d high + 1.5x volume) ya PULLBACK (uptrend mein dip + reversal candle) -> not extended (<3 ATR from EMA21),
1.5R room -> Score 0-100. SPY bearish ho to new longs block. Stop = 1.5 ATR, T1 = 2R, T2 = 3R, size = 1% risk.
Alert dedup: same stock+setup 5 din tak dobara nahi.
