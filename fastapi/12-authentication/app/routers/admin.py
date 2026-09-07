"""Admin routes.

The guard is declared once on the router, so a route added later is protected
by default rather than by whoever adds it remembering - the same reasoning as
module 09, now backed by real identity rather than a shared key.
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from app.dependencies import AdminUser, DbSession, Pagination, UserDep, require_admin
from app.errors import ForbiddenError
from app.models import Note, Role, User
from app.schemas import ERROR_RESPONSES, RoleChange, UserPage, UserRead

logger = logging.getLogger("api.admin")

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses=ERROR_RESPONSES,
)


@router.get("/users", response_model=UserPage, summary="List every user")
def list_users(db: DbSession, page: Pagination) -> dict:
    """Return all users. Admin only."""
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(select(User).order_by(User.id).limit(page.limit).offset(page.offset)).all()
    return {
        "total": total,
        "count": len(users),
        "limit": page.limit,
        "offset": page.offset,
        "items": users,
    }


@router.get("/stats", summary="Counts across the whole system")
def stats(db: DbSession) -> dict:
    """Aggregate counts. Protected without this function mentioning it."""
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "admins": db.scalar(select(func.count()).select_from(User).where(User.role == Role.ADMIN)) or 0,
        "notes": db.scalar(select(func.count()).select_from(Note)) or 0,
    }


@router.patch("/users/{user_id}/role", response_model=UserRead, summary="Change a user's role")
def change_role(user: UserDep, payload: RoleChange, admin: AdminUser) -> User:
    """Promote or demote a user.

    An admin cannot demote themselves. Without that check, the last remaining
    admin can lock every administrator out of the system with one request and
    no way back short of editing the database by hand.
    """
    if user.id == admin.id and payload.role != Role.ADMIN:
        raise ForbiddenError("An administrator cannot remove their own admin role")
    logger.info("admin %s set user %s role to %s", admin.id, user.id, payload.role)
    user.role = payload.role
    return user


@router.post("/users/{user_id}/deactivate", response_model=UserRead, summary="Disable an account")
def deactivate(user: UserDep, admin: AdminUser) -> User:
    """Disable an account.

    Takes effect on the account's next request, not when its token expires,
    because get_current_user re-reads is_active from the database every time.
    """
    if user.id == admin.id:
        raise ForbiddenError("An administrator cannot deactivate their own account")
    logger.info("admin %s deactivated user %s", admin.id, user.id)
    user.is_active = False
    return user


@router.post("/users/{user_id}/activate", response_model=UserRead, summary="Re-enable an account")
def activate(user: UserDep, admin: AdminUser) -> User:
    """Re-enable a disabled account."""
    user.is_active = True
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
def delete_user(user: UserDep, admin: AdminUser, db: DbSession) -> None:
    """Delete a user and cascade to their notes."""
    if user.id == admin.id:
        raise ForbiddenError("An administrator cannot delete their own account")
    db.delete(user)
