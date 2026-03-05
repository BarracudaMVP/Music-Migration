from fastapi import APIRouter

from core.services.base import Capability
from core.services.registry import ServiceRegistry

router = APIRouter()


@router.get("")
async def list_services():
    return [
        {
            "id": a.id,
            "name": a.name,
            "capabilities": [c.name for c in Capability if a.can(c)],
        }
        for a in ServiceRegistry.all()
    ]


@router.get("/matrix")
async def get_matrix():
    return ServiceRegistry.get_matrix()
