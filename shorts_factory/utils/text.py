"""Лёгкая очистка Reddit-разметки и подсчёт слов.

Полноценная адаптация текста под 30-60 секунд озвучки — задача модуля
Text Processor; здесь только то, что нужно скраперу, чтобы честно отфильтровать
пост по длине (markdown-мусор не должен считаться словами).
"""

from __future__ import annotations

import html
import re

_DELETED_MARKERS = {"[removed]", "[deleted]", "[removed by reddit]", ""}

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")
_URL = re.compile(r"https?://\S+|www\.\S+")
_SUBREDDIT_OR_USER = re.compile(r"(?<![\w/])/?[ru]/[A-Za-z0-9_\-]+")
_QUOTE_MARK = re.compile(r"^\s{0,3}>+\s?", re.MULTILINE)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_MARK = re.compile(r"^\s{0,3}(?:[*+-]|\d+\.)\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(?<!\\)(\*{1,3}|_{1,3}|~{2})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~])")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_HR = re.compile(r"^\s*(?:\*{3,}|-{3,}|_{3,})\s*$", re.MULTILINE)
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*|\d+", re.UNICODE)


def strip_markdown(text: str) -> str:
    """Убирает Reddit/markdown-разметку, ссылки и HTML-сущности."""
    if not text:
        return ""
    text = html.unescape(text)
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub(" ", text)
    text = _SUBREDDIT_OR_USER.sub(" ", text)
    text = _TABLE_ROW.sub(" ", text)
    text = _HR.sub(" ", text)
    text = _QUOTE_MARK.sub("", text)
    text = _HEADING.sub("", text)
    text = _LIST_MARK.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _ESCAPED.sub(r"\1", text)
    text = _SPACES.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def count_words(text: str) -> int:
    """Считает слова в уже очищенном или сыром тексте."""
    return len(_WORD.findall(strip_markdown(text)))


def is_deleted(text: str | None) -> bool:
    """True для удалённых/пустых тел постов и комментариев."""
    if text is None:
        return True
    return text.strip().lower() in _DELETED_MARKERS
