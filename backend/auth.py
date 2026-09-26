import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import User, get_db

JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(hours=24)
MIN_PASSWORD_LENGTH = 8

_password_hash = PasswordHash.recommended()  # argon2
# auto_error=False so a missing header yields our own French 401, not FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET n’est pas configuré sur le serveur")
    return secret


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_LIFETIME}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Connexion requise ou expirée, merci de vous reconnecter",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: str
    password: str


def _user_payload(user: User) -> dict:
    return {"id": str(user.id), "email": user.email, "created_at": user.created_at}


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": _user_payload(user)}


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")
    user = User(email=email, password_hash=_password_hash.hash(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == _normalize_email(body.email)))
    # Same message for unknown email and wrong password (spec FR-002).
    if user is None or not _password_hash.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return _token_response(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)
