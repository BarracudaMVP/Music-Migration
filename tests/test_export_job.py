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


# GET /migrate/{id}/export-file endpoint removed (MM-82) — Jinja2 web UI deleted.
# SPA export uses GET /api/v1/migrations/{id}/export (tested in test_mm98.py).
