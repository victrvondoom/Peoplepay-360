from fastapi import APIRouter
from app.models.domain import ACTIVE_DOMAINS, DOMAIN_LABELS

router = APIRouter()


@router.get("")
async def list_domains() -> list[dict]:
    return [
        {"id": domain.value, "label": label, "active": domain in ACTIVE_DOMAINS}
        for domain, label in DOMAIN_LABELS.items()
    ]
