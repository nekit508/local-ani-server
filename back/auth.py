import json

from fastapi import APIRouter, HTTPException, Body
from fastapi import Depends, Response
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from db import get_session
from models import User
from scheme import LoginIn
from security import decode_token, verify_password, create_token

router = APIRouter(prefix="/back/auth", tags=["auth"])
auth_token = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_user_by_login(
        login: str,
        session: Session
) -> User | None:
    return session.execute(select(User).where(User.login == login)).scalar_one_or_none()


def get_user_by_id(
        uid: int,
        session: Session
) -> User | None:
    return session.get(User, uid)


def get_user(
        token: str = Depends(auth_token),
        session: Session = Depends(get_session)
) -> User:
    try:
        payload = decode_token(token)
        uid = int(payload["sub"])
        cv = int(payload["cv"])

        user = get_user_by_id(uid, session)

        if user is None or user.cv != cv:
            raise ValueError

        return user

    except (PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"X-JWT-Action": '{"type":"DELETE","token":""}'},
        )

@router.post("/login")
def login(
        response: Response,
        body: LoginIn = Body(),
        session: Session = Depends(get_session)
):
    user = get_user_by_login(body.login, session)

    if user is None:
        verify_password()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials"
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials"
        )

    response.headers["X-JWT-Action"] = json.dumps({
        "type": "SAVE",
        "token": create_token(user.id, user.cv)
    })


@router.get("/me")
def me(user: User = Depends(get_user)):
    return {"id": user.id, "login": user.login, "cv": user.cv}


@router.post("/logout-all")
def logout_all(
    user: User = Depends(get_user),
    session: Session = Depends(get_session),
):
    user.cv += 1
    session.commit()
    return {"ok": True, "cv": user.cv}

@router.get("/verify")
def verify(_: User = Depends(get_user)):
    return { "ok": True }