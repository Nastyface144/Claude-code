"""HTTP-статус, по которому хостинги проверяют, что бот жив."""

import socket

import aiohttp
import pytest

from freelance_bot.app import start_status_server
from freelance_bot.config import Settings
from freelance_bot.service import PollReport, Radar
from freelance_bot.storage import Storage


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
async def running(tmp_path):
    port = free_port()
    storage = await Storage(tmp_path / "db.sqlite").connect()
    settings = Settings(bot_token="42:TEST", db_path=tmp_path / "db.sqlite", port=port)
    radar = Radar(settings, storage, bot=None)  # type: ignore[arg-type]
    runner = await start_status_server(radar, port)
    yield radar, port
    await runner.cleanup()
    await storage.close()


async def fetch(port: int) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/health") as response:
            assert response.status == 200
            return await response.json()


async def test_status_reports_alive_before_first_cycle(running):
    _radar, port = running
    payload = await fetch(port)
    assert payload["статус"] == "работает"
    assert payload["последний цикл"] == "ещё не было"


async def test_status_shows_last_cycle(running):
    radar, port = running
    radar.last_report = PollReport(fetched=59, new=3, relevant=2, sent=2, errors=[("fl", "403")])

    payload = await fetch(port)

    assert payload["последний цикл"]["получено"] == 59
    assert payload["последний цикл"]["отправлено"] == 2
    assert payload["последний цикл"]["ошибки"] == ["fl: 403"]
