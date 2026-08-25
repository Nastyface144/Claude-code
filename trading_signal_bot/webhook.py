"""HTTP-приём алертов TradingView."""

from __future__ import annotations

import hmac
import logging

from aiohttp import web

from .models import Signal
from .service import TradingEngine

log = logging.getLogger(__name__)


def _first(payload: dict, *keys: str):
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def signal_from_payload(payload: dict) -> Signal:
    """Строит Signal из тела алерта TradingView.

    Поддерживает несколько вариантов имён полей, чтобы не привязываться
    к точной формулировке JSON, который настроен в каждом отдельном алерте.
    """
    indicator = _first(payload, "indicator", "source", "strategy")
    symbol = _first(payload, "symbol", "ticker")
    timeframe = _first(payload, "timeframe", "interval", "tf")
    direction = _first(payload, "direction", "action", "side", "signal")
    price = _first(payload, "price", "close", "entry")
    stop_loss = _first(payload, "stop_loss", "sl", "stopLoss")
    take_profit = _first(payload, "take_profit", "tp", "takeProfit")
    note = _first(payload, "note", "comment", "message") or ""

    missing = [
        name
        for name, value in (
            ("indicator", indicator),
            ("symbol", symbol),
            ("timeframe", timeframe),
            ("direction", direction),
            ("price", price),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"в теле алерта не хватает полей: {', '.join(missing)}")

    return Signal(
        indicator=str(indicator),
        symbol=str(symbol),
        timeframe=str(timeframe),
        direction=str(direction),
        price=float(price),
        stop_loss=float(stop_loss) if stop_loss is not None else None,
        take_profit=float(take_profit) if take_profit is not None else None,
        note=str(note)[:300],
    )


def build_app(engine: TradingEngine, webhook_secret: str) -> web.Application:
    async def handle_webhook(request: web.Request) -> web.Response:
        secret = request.match_info.get("secret", "")
        if not webhook_secret or not hmac.compare_digest(secret, webhook_secret):
            return web.json_response({"error": "invalid secret"}, status=403)

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid JSON"}, status=400)

        if not isinstance(payload, dict):
            return web.json_response({"error": "expected a JSON object"}, status=400)

        try:
            signal = signal_from_payload(payload)
        except (ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

        result = await engine.handle_signal(signal)
        log.info(
            "Сигнал %s %s %s от %s -> %s (%s)",
            signal.symbol,
            signal.timeframe,
            signal.direction,
            signal.indicator,
            result.status,
            result.detail,
        )
        return web.json_response({"status": result.status, "detail": result.detail})

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post("/webhook/{secret}", handle_webhook)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app
