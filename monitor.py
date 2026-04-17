"""
monitor.py — Remote control & live monitoring via Telegram
Commands:
  /status    → open positions + account balance
  /price     → XAUUSD live bid/ask
  /trades    → last 10 trades from trades.json
  /close <ticket> → close a specific position
  /closeall  → close all open positions
"""

import asyncio
import json
import logging
import MetaTrader5 as mt5
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_ID        = 5611063972   # ← your Telegram user ID
MONITOR_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
POLL_INTERVAL   = 10           # seconds
TRADES_FILE     = "trades.json"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _pnl_emoji(pnl):
    return "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"


def _fmt_position(pos):
    pnl   = pos.profit
    emoji = _pnl_emoji(pnl)
    sign  = "+" if pnl >= 0 else ""
    ptype = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
    return (
        f"{emoji} *{pos.symbol}* {ptype}\n"
        f"  Ticket: `{pos.ticket}`\n"
        f"  Open: `{pos.price_open:.2f}` → Now: `{pos.price_current:.2f}`\n"
        f"  SL: `{pos.sl:.2f}` | TP: `{pos.tp:.2f}`\n"
        f"  Lot: `{pos.volume}` | P&L: `{sign}{pnl:.2f} USD`\n"
        f"  Opened: {datetime.fromtimestamp(pos.time).strftime('%H:%M:%S')}"
    )


def _fmt_account():
    info = mt5.account_info()
    if not info:
        return "⚠️ Could not fetch account info"
    sign = "+" if info.profit >= 0 else ""
    return (
        f"💰 *Account #{info.login}*\n"
        f"  Balance:     `{info.balance:.2f} {info.currency}`\n"
        f"  Equity:      `{info.equity:.2f} {info.currency}`\n"
        f"  Free Margin: `{info.margin_free:.2f} {info.currency}`\n"
        f"  Open P&L:    `{sign}{info.profit:.2f} {info.currency}`\n"
        f"  Leverage:    `1:{info.leverage}`"
    )


def close_position(pos):
    tick = mt5.symbol_info_tick(pos.symbol)
    if not tick:
        return False, f"No tick data for {pos.symbol}"

    close_type  = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    close_price = tick.bid            if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       pos.symbol,
        "volume":       pos.volume,
        "type":         close_type,
        "position":     pos.ticket,
        "price":        close_price,
        "deviation":    20,
        "magic":        999999,
        "comment":      "Remote close",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        return False, "MT5 returned None — AutoTrading may be OFF or market closed"
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, f"Closed ticket {pos.ticket} | P&L: {pos.profit:+.2f} USD"
    return False, f"Failed retcode={result.retcode}: {result.comment}"


# ── Command handlers ──────────────────────────────────────────────────────────
async def cmd_status(event):
    try:
        positions = mt5.positions_get()
        acc_block = _fmt_account()

        if not positions:
            await event.respond(f"{acc_block}\n\n📭 No open positions right now.", parse_mode="markdown")
            return

        total_pnl = sum(p.profit for p in positions)
        sign      = "+" if total_pnl >= 0 else ""
        lines     = [
            acc_block,
            f"\n📊 *{len(positions)} open position(s)* | Total P&L: `{sign}{total_pnl:.2f} USD`\n"
        ]
        for pos in positions:
            lines.append(_fmt_position(pos))
        await event.respond("\n\n".join(lines), parse_mode="markdown")
    except Exception as e:
        log.exception(f"cmd_status error: {e}")
        await event.respond(f"❌ Error: {e}")


async def cmd_price(event):
    try:
        lines = []
        for sym in MONITOR_SYMBOLS:
            tick = mt5.symbol_info_tick(sym)
            if tick:
                spread = round((tick.ask - tick.bid) * (10 if "JPY" not in sym else 100), 1)
                lines.append(f"*{sym}*  Bid: `{tick.bid:.2f}`  Ask: `{tick.ask:.2f}`  Spread: `{spread}`")
            else:
                lines.append(f"*{sym}*  ❌ unavailable")
        await event.respond("\n".join(lines), parse_mode="markdown")
    except Exception as e:
        log.exception(f"cmd_price error: {e}")
        await event.respond(f"❌ Error: {e}")


async def cmd_trades(event):
    try:
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                trades = json.load(f)
        except FileNotFoundError:
            await event.respond("📭 No trades logged yet.")
            return
        except json.JSONDecodeError:
            await event.respond("⚠️ trades.json is corrupted.")
            return

        if not trades:
            await event.respond("📭 No trades logged yet.")
            return

        recent = sorted(trades, key=lambda t: t.get("time", ""), reverse=True)[:10]
        lines  = [f"📋 *Last {len(recent)} trade(s):*\n"]
        for t in recent:
            action = t.get("action", "?")
            emoji  = "🟢" if action == "BUY" else "🔴"
            tp_raw = t.get('tp', 0)
            tp_str = "/".join(f"{v:.2f}" for v in tp_raw) if isinstance(tp_raw, list) else f"{float(tp_raw):.2f}"
            lines.append(
                f"{emoji} *{t.get('symbol', '?')}* {action} | "
                f"Entry: `{float(t.get('entry', 0)):.2f}` | "
                f"TP: `{tp_str}` | "
                f"SL: `{float(t.get('sl', 0)):.2f}` | "
                f"Lot: `{t.get('lot')}` | "
                f"`{t.get('time', '')}`"
            )
        await event.respond("\n".join(lines), parse_mode="markdown")
    except Exception as e:
        log.exception(f"cmd_trades error: {e}")
        await event.respond(f"❌ Error: {e}")


async def cmd_close(event):
    try:
        parts = event.raw_text.strip().split()
        if len(parts) < 2 or not parts[1].isdigit():
            await event.respond("Usage: `/close <ticket>`", parse_mode="markdown")
            return

        ticket    = int(parts[1])
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            await event.respond(f"❌ No open position with ticket `{ticket}`", parse_mode="markdown")
            return

        ok, msg = close_position(positions[0])
        await event.respond(("✅ " if ok else "❌ ") + msg)
    except Exception as e:
        log.exception(f"cmd_close error: {e}")
        await event.respond(f"❌ Error: {e}")


async def cmd_closeall(event):
    try:
        positions = mt5.positions_get()
        if not positions:
            await event.respond("📭 No open positions to close.")
            return

        await event.respond(f"⚠️ Closing {len(positions)} position(s)...")
        results = []
        for pos in positions:
            ok, msg = close_position(pos)
            results.append(("✅ " if ok else "❌ ") + msg)
        await event.respond("\n".join(results))
    except Exception as e:
        log.exception(f"cmd_closeall error: {e}")
        await event.respond(f"❌ Error: {e}")


# ── Auto position monitor ─────────────────────────────────────────────────────
async def position_monitor(client, notify_id):
    try:
        me = await client.get_entity(notify_id)
    except Exception:
        me = "me"

    async def notify(msg):
        try:
            await client.send_message(me, msg, parse_mode="markdown")
        except Exception as e:
            log.warning(f"Notify failed: {e}")

    known = {p.ticket for p in (mt5.positions_get() or [])}
    log.info(f"Monitor started — tracking {len(known)} existing position(s)")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            current_positions = mt5.positions_get() or []
            current    = {p.ticket: p for p in current_positions}
            current_ids = set(current.keys())

            for ticket in current_ids - known:
                pos = current[ticket]
                msg = f"🚀 *New position opened!*\n\n{_fmt_position(pos)}\n\n{_fmt_account()}"
                log.info(f"Notifying: new position {ticket}")
                await notify(msg)

            for ticket in known - current_ids:
                now     = datetime.now()
                from_dt = now - timedelta(hours=24)
                history = mt5.history_deals_get(int(from_dt.timestamp()), int(now.timestamp()), group="*")
                deal    = None
                if history:
                    matches = [d for d in history if d.position_id == ticket]
                    if matches:
                        deal = matches[-1]

                if deal:
                    pnl   = deal.profit
                    sign  = "+" if pnl >= 0 else ""
                    emoji = "🟢" if pnl >= 0 else "🔴"
                    msg   = (
                        f"{emoji} *Position closed*\n"
                        f"  Ticket: `{ticket}`\n"
                        f"  Symbol: `{deal.symbol}`\n"
                        f"  P&L: `{sign}{pnl:.2f} USD`\n"
                        f"  Time: {datetime.fromtimestamp(deal.time).strftime('%H:%M:%S')}\n\n"
                        f"{_fmt_account()}"
                    )
                else:
                    msg = f"📕 Position `{ticket}` was closed.\n\n{_fmt_account()}"

                log.info(f"Notifying: closed position {ticket}")
                await notify(msg)

            known = current_ids

        except Exception as e:
            log.exception(f"Monitor loop error: {e}")
            # never stop the loop — just log and continue


async def cmd_log(event):
    try:
        import os
        from fpdf import FPDF

        log_path = "bot.log"
        if not os.path.exists(log_path):
            await event.respond("📭 No log file found.")
            return

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.set_margins(10, 10, 10)

        for line in lines:
            # sanitize non-latin chars that fpdf can't encode
            safe = line.rstrip().encode("latin-1", errors="replace").decode("latin-1")
            pdf.cell(0, 4, safe, ln=True)

        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        pdf_path = f"log_{date_str}.pdf"
        pdf.output(pdf_path)

        await event.client.send_file(
            await event.get_chat(),
            pdf_path,
            caption=f"📄 bot.log — exported {date_str}"
        )

        os.remove(pdf_path)  # clean up after sending

    except Exception as e:
        log.exception(f"cmd_log error: {e}")
        await event.respond(f"❌ Error: {e}")


# ── Register commands ─────────────────────────────────────────────────────────
def register_commands(client):
    from telethon import events as tl_events

    async def guard(handler, event):
        """Only accept commands from ADMIN_ID."""
        try:
            sender = event.sender_id
            if ADMIN_ID and sender != ADMIN_ID:
                try:
                    me = await client.get_me()
                    if sender != me.id:
                        return
                except Exception:
                    return
            await handler(event)
        except Exception as e:
            log.exception(f"Guard error: {e}")

    client.add_event_handler(lambda e: guard(cmd_status,   e), tl_events.NewMessage(pattern=r"(?i)^/status"))
    client.add_event_handler(lambda e: guard(cmd_price,    e), tl_events.NewMessage(pattern=r"(?i)^/price"))
    client.add_event_handler(lambda e: guard(cmd_trades,   e), tl_events.NewMessage(pattern=r"(?i)^/trades"))
    client.add_event_handler(lambda e: guard(cmd_close,    e), tl_events.NewMessage(pattern=r"(?i)^/close\b"))
    client.add_event_handler(lambda e: guard(cmd_closeall, e), tl_events.NewMessage(pattern=r"(?i)^/closeall"))
    client.add_event_handler(lambda e: guard(cmd_log,      e), tl_events.NewMessage(pattern=r"(?i)^/log"))
