"""Authentication (JWT + bcrypt) and role / ownership checks, enforced on the server."""
from dataclasses import dataclass
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import Application, User
from app.services.dates import now_ist
from app.settings import settings

APPLICANT, KYC_OFFICER, COMPLIANCE_OFFICER = "APPLICANT", "KYC_OFFICER", "COMPLIANCE_OFFICER"
STAFF = {KYC_OFFICER, COMPLIANCE_OFFICER}
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def _secret() -> str:
    if not settings.jwt_secret:
        raise ApiError(503, "AUTH_NOT_CONFIGURED", "JWT_SECRET is not configured on the server")
    return settings.jwt_secret


# "Sign in as" choice -> roles the session will carry
LOGIN_ROLES = {
    "APPLICANT": [APPLICANT],
    "KYC_OFFICER": [KYC_OFFICER],
    "COMPLIANCE_OFFICER": [COMPLIANCE_OFFICER],
    "KYC_AND_COMPLIANCE": [KYC_OFFICER, COMPLIANCE_OFFICER],
}
LOGIN_ROLE_LABELS = {"APPLICANT": "an Applicant", "KYC_OFFICER": "a KYC Officer",
                     "COMPLIANCE_OFFICER": "a Compliance Officer",
                     "KYC_AND_COMPLIANCE": "both KYC Officer and Compliance Officer"}


def session_roles(user: User, login_role: str | None) -> list[str]:
    """Roles for this session. The account must hold every role it signs in as (else 403)."""
    if login_role is None:
        return user.role_list
    wanted = LOGIN_ROLES[login_role]
    if not set(wanted) <= set(user.role_list):
        raise ApiError(403, "ROLE_NOT_ASSIGNED",
                       f"This account is not {LOGIN_ROLE_LABELS[login_role]}. Choose the role you were given.",
                       [{"field": "role", "message": "This account does not have this role"}])
    return wanted


def create_token(user: User, roles: list[str] | None = None) -> str:
    now = now_ist()
    payload = {"sub": user.id, "roles": roles if roles is not None else user.role_list, "iat": now,
               "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, _secret(), algorithm="HS256")


@dataclass
class CurrentUser:
    id: str
    username: str
    full_name: str
    roles: list[str]

    def has(self, *roles: str) -> bool:
        return bool(set(roles) & set(self.roles))

    @property
    def is_staff(self) -> bool:
        return self.has(*STAFF)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> CurrentUser:
    if creds is None:
        raise ApiError(401, "UNAUTHENTICATED", "Please log in")
    try:
        payload = jwt.decode(creds.credentials, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "UNAUTHENTICATED", "Your session has expired; please log in again")
    except jwt.InvalidTokenError:
        raise ApiError(401, "UNAUTHENTICATED", "Invalid login token")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED", "User no longer exists")
    # Session roles = roles chosen at sign-in, limited to what the account still has in the DB.
    token_roles = payload.get("roles") or user.role_list
    roles = [r for r in user.role_list if r in token_roles]
    return CurrentUser(user.id, user.username, user.full_name, roles)


def require_roles(*roles: str):
    """Dependency factory: 403 unless the user has at least one of the roles."""
    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has(*roles):
            raise ApiError(403, "FORBIDDEN", "Your role is not allowed to do this")
        return user
    return dependency


def get_application_for(db: Session, application_id: str, user: CurrentUser) -> Application:
    """Staff see any application; an applicant only their own. Not yours -> 404 (don't leak existence)."""
    app = db.get(Application, application_id)
    if app is None or not (user.is_staff or app.owner_id == user.id):
        raise ApiError(404, "NOT_FOUND", "Application not found")
    return app
