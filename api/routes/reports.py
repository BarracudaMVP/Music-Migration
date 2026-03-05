"""Reports routes: not-found file download."""
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from api.deps import verify_internal_token

router = APIRouter(dependencies=[Depends(verify_internal_token)])


@router.get("/{migration_id}/not-found", response_class=PlainTextResponse)
async def get_not_found_report(migration_id: int):
    path = f"not_found_{migration_id}.txt"
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    with open(path, encoding="utf-8") as f:
        return f.read()
