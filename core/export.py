"""Standalone library export: fetch tracks from a source service → CSV/JSON bytes."""
from __future__ import annotations

import csv
import io
import json

from core.services.base import Capability
from core.services.registry import ServiceRegistry


async def export_library(service_id: str, token: str, fmt: str = "csv") -> bytes:
    """
    Fetch liked tracks from `service_id` using `token` and return file bytes.
    `fmt` is 'csv' or 'json'. Output columns: artist, title.
    """
    adapter = ServiceRegistry.get(service_id)
    if not adapter.can(Capability.EXPORT_TRACKS):
        raise ValueError(f"Сервис {adapter.name} не поддерживает экспорт библиотеки")

    tracks = await adapter.fetch_liked_tracks(token)  # list[{artist, title}]

    if fmt == "json":
        return json.dumps(tracks, ensure_ascii=False, indent=2).encode("utf-8")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["artist", "title"], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(tracks)
    return buf.getvalue().encode("utf-8")


def exportable_services() -> list:
    """Return adapters that support EXPORT_TRACKS, for use in templates."""
    return [a for a in ServiceRegistry.all() if a.can(Capability.EXPORT_TRACKS)]
