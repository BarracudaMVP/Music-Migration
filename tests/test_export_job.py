"""Tests for MM-78: async export job and export-file endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# run_export_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_export_job_success():
    from worker.tasks import run_export_job

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock()
    ctx = {"redis": redis_mock}

    export_bytes = b"artist,title\nArtist A,Song A\n"

    with (
        patch("worker.tasks._get_user_lang", AsyncMock(return_value="ru")),
        patch("core.db.update_migration", AsyncMock()) as mock_update,
        patch("core.export.export_library", AsyncMock(return_value=export_bytes)),
        patch("worker.notifications.notify_telegram", AsyncMock()),
        patch("worker.notifications.migration_failed_text", return_value="failed"),
    ):
        await run_export_job(ctx, 42, "yandex_music", "token123", "csv", "user1")

    # Redis должен получить данные с ключом export_data:42
    redis_mock.set.assert_called_once()
    call_args = redis_mock.set.call_args
    assert call_args[0][0] == "export_data:42"
    assert call_args[0][1] == export_bytes

    # Статус должен стать done + result_path=csv
    assert any(c[1].get("result_path") == "csv" for c in mock_update.call_args_list)


@pytest.mark.asyncio
async def test_run_export_job_sets_running_then_done():
    from worker.tasks import run_export_job

    redis_mock = AsyncMock()
    ctx = {"redis": redis_mock}
    update_calls = []

    async def track_update(mid, **kw):
        update_calls.append(kw)

    with (
        patch("worker.tasks._get_user_lang", AsyncMock(return_value="ru")),
        patch("core.db.update_migration", side_effect=track_update),
        patch("core.export.export_library", AsyncMock(return_value=b"data")),
        patch("worker.notifications.notify_telegram", AsyncMock()),
    ):
        await run_export_job(ctx, 1, "spotify", "tok", "json", "u1")

    assert update_calls[0] == {"status": "running"}
    assert update_calls[1].get("status") == "done"
    assert update_calls[1].get("result_path") == "json"


@pytest.mark.asyncio
async def test_run_export_job_failure_sets_failed():
    from worker.tasks import run_export_job

    redis_mock = AsyncMock()
    ctx = {"redis": redis_mock}

    with (
        patch("worker.tasks._get_user_lang", AsyncMock(return_value="ru")),
        patch("core.db.update_migration", AsyncMock()) as mock_update,
        patch("core.export.export_library", AsyncMock(side_effect=RuntimeError("boom"))),
        patch("worker.notifications.notify_telegram", AsyncMock()),
        patch("worker.notifications.migration_failed_text", return_value="failed"),
    ):
        with pytest.raises(RuntimeError):
            await run_export_job(ctx, 99, "yandex_music", "tok", "csv", "u1")

    # status=failed должен быть выставлен
    failed_calls = [c for c in mock_update.call_args_list if c[1].get("status") == "failed"]
    assert len(failed_calls) == 1


# ---------------------------------------------------------------------------
# GET /migrate/{id}/export-file
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture(autouse=True)
def ensure_services_registered():
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.soundcloud.adapter import SoundCloudAdapter
    from core.services.file.adapter import FileAdapter
    from core.services.spotify.adapter import SpotifyAdapter
    for a in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter(), SpotifyAdapter()]:
        ServiceRegistry.register(a)


@pytest.mark.asyncio
async def test_export_file_endpoint_returns_csv(app):
    from httpx import AsyncClient, ASGITransport

    csv_bytes = b"artist,title\nDJ A,Song B\n"
    migration = {
        "id": 5, "user_id": "u1", "status": "done",
        "result_path": "csv", "to_service": "file",
        "from_service": "yandex_music", "created_at": None,
        "soundcloud_user_id": None, "user_migration_number": 1,
    }

    arq_mock = MagicMock()
    arq_mock.get = AsyncMock(return_value=csv_bytes)

    with (
        patch("api.routes.web.get_migration", AsyncMock(return_value=migration)),
        patch("api.main.get_arq_pool", return_value=arq_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/migrate/5/export-file")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert b"artist,title" in resp.content
    assert "attachment" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_file_endpoint_404_if_not_done(app):
    from httpx import AsyncClient, ASGITransport

    migration = {
        "id": 6, "user_id": "u1", "status": "running",
        "result_path": None, "to_service": "file",
        "from_service": "yandex_music", "created_at": None,
        "soundcloud_user_id": None, "user_migration_number": 1,
    }

    with patch("api.routes.web.get_migration", AsyncMock(return_value=migration)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/migrate/6/export-file")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_file_endpoint_410_if_redis_expired(app):
    from httpx import AsyncClient, ASGITransport

    migration = {
        "id": 7, "user_id": "u1", "status": "done",
        "result_path": "json", "to_service": "file",
        "from_service": "spotify", "created_at": None,
        "soundcloud_user_id": None, "user_migration_number": 2,
    }

    arq_mock = MagicMock()
    arq_mock.get = AsyncMock(return_value=None)  # TTL expired

    with (
        patch("api.routes.web.get_migration", AsyncMock(return_value=migration)),
        patch("api.main.get_arq_pool", return_value=arq_mock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/migrate/7/export-file")

    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_export_file_endpoint_404_if_migration_missing(app):
    from httpx import AsyncClient, ASGITransport

    with patch("api.routes.web.get_migration", AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/migrate/999/export-file")

    assert resp.status_code == 404
