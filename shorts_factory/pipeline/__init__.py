"""Модули пайплайна.

Реализовано:
    reddit_scraper — модуль 1: сбор историй с Reddit в очередь.

В плане (см. README, раздел «Дорожная карта»):
    text_processor, tts, subtitles, background, assembler, uploader, orchestrator
"""

from .reddit_scraper import RedditScraper, ScrapeReport

__all__ = ["RedditScraper", "ScrapeReport"]
