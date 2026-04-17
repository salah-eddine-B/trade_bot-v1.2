# Telegram → MT5 Auto Trading Bot

Automatically reads trading signals from a Telegram channel and executes them on MetaTrader 5. Includes remote control from your phone and full activity logging.

---

## What it does

- Listens to a Telegram channel for trading signals
- Parses the signal (symbol, action, entry, SL, TPs)
- Opens trades on MT5 with proper lot sizing split across all TPs
- Calculates SL dynamically based on account balance (risk %)
- Logs every trade to `trades.json` and all activity to `bot.log`
- Sends account info (balance, equity, P&L) with every notification
- Lets you monitor and control trades remotely via Telegram commands
- Never crashes on errors — all exceptions are caught and logged

---

## Requirements

- Windows PC with **MetaTrader 5** installed and logged into a broker account
- Python 3.10+
- A Telegram account (not a bot token — your actual account)

---

## Installation

**1. Clone the project**

```bash
git clone https://github.com/yourname/trade-bot.git
cd trade-bot
```

**2. Install Python dependencies**

```bash
pip install telethon MetaTrader5
```

**3. Enable Algo Trading in MT5**

Open MT5 → Tools → Options → Expert Advisors → check **"Allow automated trading"**

Also make sure the symbol you trade (e.g. `XAUUSD`) is visible in your Market Watch panel.

---

## Configuration

Open `bot.py` and set these values at the top:

```python
api_id   = YOUR_API_ID       # from my.telegram.org
api_hash = "YOUR_API_HASH"   # from my.telegram.org
CHANNEL_ID = -100XXXXXXXXXX  # target channel ID
LOT = 0.01                   # base lot size per signal
RISK_PERCENT = 0.13          # 13% of balance = ~8 USD on a 60 USD account
```

### Getting your Telegram API credentials

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click **API development tools**
4. Create an app — copy `api_id` and `api_hash`

### Getting a channel ID

Run `get_channels.py` — it prints all channels you're a member of with their IDs:

```bash
python get_channels.py
```

### Setting up remote control (optional but recommended)

Open `monitor.py` and set your Telegram user ID:

```python
ADMIN_ID = 123456789  # your Telegram user ID
```

Get your ID by messaging [@userinfobot](https://t.me/userinfobot) on Telegram.

---

## Running the bot

```bash
python bot.py
```

The first time you run it, Telethon will ask for your phone number and a confirmation code to log in. After that it saves a `session.session` file and logs in automatically.

On startup the bot sends you a message like:

```
🤖 Bot started

💰 Account #12345678
  Balance:     60.00 USD
  Equity:      60.00 USD
  Free Margin: 60.00 USD
  Leverage:    1:100
  Open P&L:    +0.00 USD

⚙️ Risk per trade: 13% ≈ 7.80 USD
📡 Monitoring positions every 10s
```

---

## Risk-based Stop Loss

Instead of a fixed SL distance, the bot calculates SL dynamically so the maximum loss per trade equals `RISK_PERCENT` of your current balance.

```
risk_usd     = balance × RISK_PERCENT
sl_distance  = (risk_usd / (tick_value × lot)) × tick_size
```

Example on a 60 USD account with `RISK_PERCENT = 0.13`:
- Max loss = **7.80 USD** per trade
- SL distance is auto-calculated from MT5 tick data for the symbol

If the signal includes an explicit SL, the bot uses whichever distance is smaller (signal SL vs balance-based SL) to stay safe.

If the calculation fails for any reason, it falls back to a 15-point default.

---

## Signal format

The bot understands signals in this format:

```
XAUUSD GOLD SELL 4702/4706
TP 4698 TP 4694 TP 4690 TP 4686 TP 4682 TP 4678
SL 4720
```

| Part | Description |
|---|---|
| `XAUUSD` or `GOLD` | Symbol (currently supports XAUUSD) |
| `BUY` / `SELL` | Trade direction |
| `4702/4706` | Entry range — bot averages it |
| `TP 4698 TP 4694 ...` | One trade opened per TP |
| `SL 4720` | Stop loss — auto-calculated from balance if missing |

---

## Remote control from your phone

Once `ADMIN_ID` is set, message yourself on Telegram while the bot is running:

| Command | Description |
|---|---|
| `/status` | Account info + all open positions with live P&L |
| `/price` | Live bid/ask for XAUUSD, EURUSD, GBPUSD |
| `/trades` | Last 10 logged trades |
| `/close 100123` | Close a specific position by ticket number |
| `/closeall` | Close all open positions |

Every automatic notification (position opened/closed) also includes a full account snapshot so you always know your current balance and P&L.

---

## Logging

All activity is written to `bot.log` in the project folder:

```
2026-04-08 10:40:56 [INFO]    MT5 connected
2026-04-08 10:40:57 [INFO]    Bot is running...
2026-04-08 10:41:02 [INFO]    New message received: ...
2026-04-08 10:41:02 [WARNING] Invalid signal — missing fields: symbol=None ...
2026-04-08 10:41:10 [INFO]    Trade opened | TP=3210.50 | ticket=123456
2026-04-08 10:41:10 [ERROR]   Trade failed | retcode=10016 | ...
```

Log levels used:
- `INFO` — normal activity (bot start, signals received, trades opened)
- `WARNING` — invalid signals, missing SL, fallback defaults used
- `ERROR` — trade failures, MT5 errors
- `CRITICAL` — fatal startup failures

---

## Project structure

```
├── bot.py              # Main bot — signal listener + trade execution
├── monitor.py          # Remote control + position monitor
├── parser.py           # Signal text parser
├── trades.json         # Trade log (auto-created)
├── bot.log             # Activity log (auto-created)
├── session.session     # Telegram session (auto-created on first login)
├── get_channels.py     # Helper: list your Telegram channels
├── get_last_messages.py# Helper: read recent messages from a channel
├── test_parser.py      # Test the signal parser
├── test_mt5.py         # Test MT5 connection
└── test_telegram.py    # Test Telegram connection
```

---

## Important notes

**One machine at a time** — never run the bot on two machines using the same `session.session` file simultaneously. Telegram will invalidate the session. Delete the old `session.session` before switching machines.

**Demo account first** — test on a demo account before going live. Verify trades are opening correctly with the right SL/TP.

**Lot sizing** — `LOT` in `bot.py` is the total lot per signal. If a signal has 6 TPs, it splits across 6 trades. Make sure your broker's minimum lot allows this.

**Market hours** — MT5 will reject orders when the market is closed. The bot logs the error and keeps running.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `MT5 initialization failed` | Make sure MT5 is open and logged in |
| `Invalid stops` | SL or TP is on the wrong side of the price — market moved since the signal |
| `AuthKeyDuplicatedError` | Delete `session.session` and restart — ran on two machines at once |
| `Symbol not available` | Add the symbol to MT5 Market Watch |
| `SL calc failed` | Check that the symbol has valid tick data in MT5; bot falls back to 15 pts |
| `/trades` shows nothing | `trades.json` doesn't exist yet — open a trade first |
