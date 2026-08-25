"""Проверка агрегированного сетапа через Claude перед отправкой ордера."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .config import Settings
from .models import Setup
from .risk import RiskResult

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты — риск-аналитик проп-трейдинговой команды. Тебе присылают сетап, собранный "
    "из подтверждений нескольких независимых индикаторов TradingView по одному символу "
    "и таймфрейму. У тебя НЕТ доступа к живым котировкам или графику — суди только по "
    "переданным числам и заметкам индикаторов. Проверь сетап на внутреннюю согласованность: "
    "не противоречат ли заметки индикаторов направлению сделки, адекватны ли стоп и тейк "
    "относительно цены входа и соотношения риск/прибыль, нет ли явных признаков того, что "
    "индикаторы сработали на разной логике (например, один трендовый, другой контр-трендовый, "
    "и это видно из заметок). Не одобряй сделку только из уважения к числу подтверждений — "
    "оценивай именно согласованность и адекватность параметров. Отвечай кратко и по делу."
)


class AIVerdict(BaseModel):
    approve: bool = Field(description="Одобрить ли отправку ордера трейдеру")
    confidence: int = Field(ge=0, le=100, description="Уверенность в оценке, 0-100")
    reasoning: str = Field(description="Короткое обоснование на русском, 1-3 предложения")
    warnings: list[str] = Field(default_factory=list, description="Конкретные красные флаги, если есть")


@dataclass(slots=True)
class AIOutcome:
    ran: bool
    verdict: AIVerdict | None
    error: str = ""


def _build_prompt(setup: Setup, risk: RiskResult, settings: Settings) -> str:
    notes = "\n".join(
        f"- {s.indicator}: цена={s.price}, стоп={s.stop_loss}, тейк={s.take_profit}, "
        f"заметка={s.note or '—'}"
        for s in setup.signals
    )
    return (
        f"Символ: {setup.symbol}\n"
        f"Таймфрейм: {setup.timeframe}\n"
        f"Направление: {'LONG' if setup.direction == 'buy' else 'SHORT'}\n"
        f"Подтвердили ({len(setup.indicators)} из {settings.total_indicators}): "
        f"{', '.join(setup.indicators)}\n\n"
        f"Сигналы по каждому индикатору:\n{notes}\n\n"
        f"Рассчитанный ордер:\n"
        f"Вход: {risk.entry}\n"
        f"Стоп: {risk.stop_loss}\n"
        f"Тейк: {risk.take_profit}\n"
        f"Risk:Reward: {risk.reward_ratio:.2f}\n"
        f"Риск сделки: {risk.risk_pct:.2f}% от баланса счёта\n"
    )


async def review_setup(setup: Setup, risk: RiskResult, settings: Settings) -> AIOutcome:
    if not settings.ai_enabled:
        return AIOutcome(ran=False, verdict=None, error="ИИ-проверка выключена (AI_ENABLED=false)")
    if not settings.anthropic_api_key:
        return AIOutcome(ran=False, verdict=None, error="Не задан ANTHROPIC_API_KEY")

    import anthropic

    prompt = _build_prompt(setup, risk, settings)

    try:
        async with anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
            response = await client.messages.parse(
                model=settings.ai_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_format=AIVerdict,
                output_config={"effort": "medium"},
            )
    except anthropic.AuthenticationError:
        log.error("Anthropic: неверный API-ключ")
        return AIOutcome(ran=False, verdict=None, error="Неверный ANTHROPIC_API_KEY")
    except anthropic.RateLimitError as exc:
        log.warning("Anthropic: rate limit: %s", exc)
        return AIOutcome(ran=False, verdict=None, error="Превышен лимит запросов к Claude API")
    except anthropic.APIStatusError as exc:
        log.warning("Anthropic: ошибка API %s: %s", exc.status_code, exc.message)
        return AIOutcome(ran=False, verdict=None, error=f"Ошибка Claude API ({exc.status_code})")
    except anthropic.APIConnectionError as exc:
        log.warning("Anthropic: сетевая ошибка: %s", exc)
        return AIOutcome(ran=False, verdict=None, error="Нет соединения с Claude API")

    verdict = response.parsed_output
    if verdict is None:
        return AIOutcome(ran=False, verdict=None, error="Claude не вернул структурированный ответ")
    return AIOutcome(ran=True, verdict=verdict)
