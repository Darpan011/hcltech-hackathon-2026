import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (APPLICANT, CurrentUser, create_token, current_user, hash_password, session_roles,
                      verify_password)
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import LoginIn, RegisterIn
from app.services import audit
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    """Self-registration creates an APPLICANT account only (self-service mode only)."""
    if not settings.self_service_onboarding:
        raise ApiError(403, "SELF_REGISTRATION_DISABLED",
                       "Accounts are opened at the branch. Please visit your branch with your documents.")
    if db.scalar(select(User).where(User.username == body.username.lower())):
        raise ApiError(409, "USERNAME_TAKEN", "That username is already taken",
                       [{"field": "username", "message": "Choose another username"}])
    user = User(id=f"U{uuid.uuid4().hex[:8]}", username=body.username.lower(),
                password_hash=hash_password(body.password), full_name=body.full_name.strip(), roles=APPLICANT)
    db.add(user)
    audit.log(db, action="USER_REGISTERED", entity="USER", entity_id=user.id, actor=(user.id, APPLICANT))
    db.commit()
    return {"id": user.id, "username": user.username, "roles": user.role_list}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "Wrong username or password")
    roles = session_roles(user, body.role)        # 403 if the account doesn't hold the chosen role
    return {"access_token": create_token(user, roles), "token_type": "bearer",
            "user": {"id": user.id, "username": user.username, "full_name": user.full_name, "roles": roles}}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "roles": user.roles}


@router.get("/config")
def auth_config() -> dict:
    """Public: tells the sign-in page whether self-registration is on."""
    return {"self_service_onboarding": settings.self_service_onboarding}
