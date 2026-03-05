from __future__ import annotations

import csv
import json
from pathlib import Path

from core.services.base import Capability, MusicServiceAdapter

_EXPORT_FIELDS = ["ym_artist", "ym_title", "ym_album", "status", "sc_url", "match_score"]
_IMPORT_REQUIRED = {"artist", "title"}


class FileAdapter(MusicServiceAdapter):
    id = "file_csv"
    name = "Файл CSV/JSON"
    capabilities = Capability.EXPORT_FILE | Capability.IMPORT_FILE

    async def export_tracks(
        self, migration_id: int, path: str, fmt: str = "csv"
    ) -> str:
        """Export migration tracks to a file. Returns the file path."""
        from core.db.crud import get_all_tracks

        tracks = await get_all_tracks(migration_id)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            out.write_text(
                json.dumps(
                    [{f: t.get(f) for f in _EXPORT_FIELDS} for t in tracks],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            with out.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(tracks)

        return str(out)

    async def import_tracks(self, path: str) -> list[dict]:
        """Read tracks from CSV/JSON. Returns list[{"artist": str, "title": str}]."""
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if src.suffix.lower() == ".json":
            raw = json.loads(src.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else []
        else:
            with src.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))

        if rows:
            cols = set(rows[0].keys())
            missing = _IMPORT_REQUIRED - cols
            if missing:
                raise ValueError(f"Missing required columns: {missing}")

        return [{"artist": r["artist"], "title": r["title"]} for r in rows]
