"""Reports routes: not-found tracks download."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from api.deps import verify_internal_token
from core.db.crud import get_all_tracks

router = APIRouter(dependencies=[Depends(verify_internal_token)])


@router.get("/{migration_id}/not-found", response_class=PlainTextResponse)
async def get_not_found_report(migration_id: int):
    """Returns all not_found + uncertain tracks for a migration as plain text."""
    tracks = await get_all_tracks(migration_id)
    not_found = [t for t in tracks if t["status"] in ("not_found",)]
    if not not_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No not-found tracks")
    lines = []
    for t in not_found:
        line = f"{t['ym_artist']} — {t['ym_title']}"
        if t.get("match_score") and t.get("sc_url"):
            line += f"  [score={t['match_score']:.0f}, uncertain: {t['sc_url']}]"
        lines.append(line)
    return "\n".join(lines)
