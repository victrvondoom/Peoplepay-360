from fastapi import APIRouter, Depends
from app.auth.dependencies import CurrentUser, get_current_user

router = APIRouter()


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
