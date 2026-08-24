"""Оценка релевантности заказа теме пользователя."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .keywords import INCLUDE_RULES, PENALTY_RULES, STOP_RULES
from .models import Order, strip_html

_NON_WORD = re.compile(r"[^0-9a-zа-я]+")


def normalize(text: str) -> str:
    """Приводим текст к виду « слово слово слово » — так проще писать правила."""
    text = html.unescape(text or "")
    text = strip_html(text).lower().replace("ё", "е")
    return " " + _NON_WORD.sub(" ", text).strip() + " "


@dataclass(frozen=True, slots=True)
class Rule:
    tag: str
    weight: int
    pattern: re.Pattern[str]

    @classmethod
    def build(cls, tag: str, weight: int, pattern: str) -> "Rule":
        return cls(tag=tag, weight=weight, pattern=re.compile(pattern))


@dataclass(slots=True)
class MatchResult:
    score: int = 0
    tags: list[str] = field(default_factory=list)
    hits: list[tuple[str, int]] = field(default_factory=list)
    blocked_by: str | None = None

    @property
    def blocked(self) -> bool:
        return self.blocked_by is not None

    def is_relevant(self, min_score: int) -> bool:
        return not self.blocked and self.score >= min_score

    def explain(self) -> str:
        if self.blocked_by:
            return f"стоп-слово: {self.blocked_by}"
        if not self.hits:
            return "совпадений нет"
        return ", ".join(f"{tag} {weight:+d}" for tag, weight in self.hits)


def _word_pattern(word: str) -> str:
    """Пользовательское слово -> регулярка. Поддерживает «*» как «любое окончание»."""
    word = normalize(word).strip()
    if not word:
        return ""
    parts = [re.escape(p).replace(r"\*", r"\w*") for p in word.split()]
    body = r"\s+".join(parts)
    suffix = "" if body.endswith(r"\w*") else r"\w*"
    return rf"\b{body}{suffix}"


class Matcher:
    """Считает балл заказа: сумма весов сработавших правил (каждое — не более раза)."""

    def __init__(
        self,
        include: list[Rule] | None = None,
        penalties: list[Rule] | None = None,
        stops: list[Rule] | None = None,
    ) -> None:
        self.include = include if include is not None else [Rule.build(*r) for r in INCLUDE_RULES]
        self.penalties = penalties if penalties is not None else [Rule.build(*r) for r in PENALTY_RULES]
        self.stops = stops if stops is not None else [Rule.build(tag, 0, pat) for tag, pat in STOP_RULES]

    def with_user_rules(
        self,
        include: list[tuple[str, int]] = (),
        exclude: list[str] = (),
    ) -> "Matcher":
        """Копия матчера с личными словами пользователя."""
        extra_include = [
            Rule.build(f"своё: {word}", weight, pattern)
            for word, weight in include
            if (pattern := _word_pattern(word))
        ]
        extra_stop = [
            Rule.build(f"своё: {word}", 0, pattern)
            for word in exclude
            if (pattern := _word_pattern(word))
        ]
        return Matcher(
            include=self.include + extra_include,
            penalties=list(self.penalties),
            stops=self.stops + extra_stop,
        )

    def match_text(self, text: str) -> MatchResult:
        normalized = normalize(text)
        result = MatchResult()

        for rule in self.stops:
            if rule.pattern.search(normalized):
                result.blocked_by = rule.tag
                return result

        seen_tags: set[str] = set()
        for rule in (*self.include, *self.penalties):
            if not rule.pattern.search(normalized):
                continue
            result.score += rule.weight
            result.hits.append((rule.tag, rule.weight))
            if rule.weight > 0 and rule.tag not in seen_tags:
                seen_tags.add(rule.tag)
                result.tags.append(rule.tag)

        result.score = max(result.score, 0)
        return result

    def match(self, order: Order) -> MatchResult:
        result = self.match_text(f"{order.title}\n{order.description}")
        if result.blocked or not result.hits:
            return result
        # Сильное совпадение прямо в заголовке — заказ почти наверняка наш.
        title = normalize(order.title)
        if any(rule.weight >= 5 and rule.pattern.search(title) for rule in self.include):
            result.score += 2
            result.hits.append(("в заголовке", 2))
        return result
