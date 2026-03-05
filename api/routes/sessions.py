"""Session CRUD routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import verify_internal_token
from core.db import delete_user_session, load_user_session, save_user_session

router = APIRouter(dependencies=[Depends(verify_internal_token)])


class SessionBody(BaseModel):
    yandex_token: str
    soundcloud_token: str


@router.get("/{user_id}")
async def get_session(user_id: str):
    session = await load_user_session(user_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.put("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def put_session(user_id: str, body: SessionBody):
    await save_user_session(user_id, body.yandex_token, body.soundcloud_token)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def del_session(user_id: str):
    await delete_user_session(user_id)
