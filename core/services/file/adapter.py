from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

from core.services.base import Capability, MusicServiceAdapter

_EXPORT_FIELDS = ["ym_artist", "ym_title", "ym_album", "status", "sc_url", "match_score"]
_IMPORT_REQUIRED = {"artist", "title"}

# Известные псевдонимы колонок для авто-определения
_ARTIST_ALIASES = {"artist", "исполнитель", "артист", "author", "ym_artist"}
_TITLE_ALIASES = {"title", "название", "трек", "song", "track", "ym_title"}


def _open_csv(path: str):
    """Открывает CSV с авто-определением BOM/кодировки."""
    with open(path, "rb") as f:
        raw = f.read(3)
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    return open(path, newline="", encoding=encoding)


class FileAdapter(MusicServiceAdapter):
    id = "file"
    name = "Файл (CSV/JSON)"
    capabilities = Capability.EXPORT_FILE | Capability.IMPORT_FILE

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    async def get_columns(self, path: str) -> list[str]:
        """Возвращает имена колонок из CSV/JSON файла."""
        src = Path(path)
        if src.suffix.lower() == ".json":
            raw = json.loads(src.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else []
            return list(rows[0].keys()) if rows else []
        fh = _open_csv(path)
        try:
            reader = csv.DictReader(fh)
            return list(reader.fieldnames or [])
        finally:
            fh.close()

    async def preview_tracks(self, path: str, limit: int = 20) -> list[dict]:
        """Возвращает первые `limit` строк как список dict (сырые данные)."""
        src = Path(path)
        if src.suffix.lower() == ".json":
            raw = json.loads(src.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else []
            return rows[:limit]
        fh = _open_csv(path)
        try:
            return list(itertools.islice(csv.DictReader(fh), limit))
        finally:
            fh.close()

    def detect_column_mapping(self, columns: list[str]) -> dict[str, str]:
        """
        Автоматически определяет artist_col и title_col по псевдонимам.
        Возвращает {"artist_col": ..., "title_col": ...} или пустые строки.
        """
        cols_lower = {c.lower(): c for c in columns}
        artist_col = next(
            (cols_lower[k] for k in _ARTIST_ALIASES if k in cols_lower), ""
        )
        title_col = next(
            (cols_lower[k] for k in _TITLE_ALIASES if k in cols_lower), ""
        )
        return {"artist_col": artist_col, "title_col": title_col}

    async def import_tracks(
        self,
        path: str,
        artist_col: str = "artist",
        title_col: str = "title",
    ) -> list[dict]:
        """
        Читает треки из CSV/JSON.
        Возвращает list[{"artist": str, "title": str}].
        """
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if src.suffix.lower() == ".json":
            raw = json.loads(src.read_text(encoding="utf-8"))
            rows = raw if isinstance(raw, list) else []
        else:
            fh = _open_csv(path)
            try:
                rows = list(csv.DictReader(fh))
            finally:
                fh.close()

        if not rows:
            return []

        if artist_col not in rows[0]:
            raise ValueError(f"Колонка '{artist_col}' не найдена в файле")
        if title_col not in rows[0]:
            raise ValueError(f"Колонка '{title_col}' не найдена в файле")

        return [
            {"artist": str(r.get(artist_col, "") or "").strip(),
             "title": str(r.get(title_col, "") or "").strip()}
            for r in rows
            if str(r.get(title_col, "") or "").strip()
        ]
