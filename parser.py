"""
parser.py — AI-powered trading signal parser using Gemini API
Replaces the old regex-based parser.
"""

import json
import time
import logging
from google import genai

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyA66zOwRtsfOZxTTXJIgROC80DRmuaf1M0"
_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"


# ── Parser ────────────────────────────────────────────────────────────────────
def parse_signal(message: str, retries: int = 3, wait: int = 1) -> dict:
    """
    Parse a trading signal message using Gemini AI.

    Returns a dict with keys:
        symbol, action, entry, tps (list), sl, valid (bool)

    If the message is not a valid signal, returns valid=False.
    """

    prompt = f"""
You are a trading signal parser.
Extract data from this Telegram message and return ONLY valid JSON, no explanation.

If the message does NOT contain a trading signal, return: {{}}

Message:
{message}

Return this exact format:
{{
  "symbol": "XAUUSD",
  "action": "BUY or SELL",
  "entry": 0,
  "tp1": 0,
  "tp2": 0,
  "sl": 0
}}

Rules:
- symbol: trading pair in uppercase (e.g. XAUUSD, EURUSD, BTCUSD)
- action: must be exactly "BUY" or "SELL"
- entry: entry price (0 if market order / not specified)
- tp1, tp2: take profit levels (0 if not given)
- sl: stop loss price (0 if not given)
"""

    for attempt in range(retries):
        try:
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )

            text = response.text.strip()

            # Extract JSON block safely
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")

            data = json.loads(text[start:end])

            # Empty response = not a signal
            if not data:
                return {"valid": False}

            symbol = data.get("symbol", "").strip().upper()
            action = data.get("action", "").strip().upper()
            entry  = float(data.get("entry") or 0)
            sl     = float(data.get("sl") or 0) or None

            # Collect TPs — skip zeros
            tps = []
            for key in ["tp1", "tp2", "tp3"]:
                val = float(data.get(key) or 0)
                if val > 0:
                    tps.append(val)

            valid = bool(symbol and action in ("BUY", "SELL"))

            return {
                "symbol": symbol,
                "action": action,
                "entry":  entry if entry > 0 else None,
                "tps":    tps,
                "sl":     sl,
                "valid":  valid,
            }

        except Exception as e:
            log.warning(f"Gemini parse attempt {attempt + 1} failed: {e}")
            time.sleep(wait)

    log.error("All Gemini parse attempts failed")
    return {"valid": False}
