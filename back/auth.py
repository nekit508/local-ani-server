import json

from fastapi import APIRouter, HTTPException, Body
from fastapi import Depends, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from starlette import status

from back.databases import main, User
from back.services.users import login_, get_user_by_token_
from scheme import LoginIn

router = APIRouter(prefix="/back/auth", tags=["auth"])
auth_token = OAuth2PasswordBearer(tokenUrl="/auth/login")

_get_session = main.gen_session

def get_user(
        token: str = Depends(auth_token),
        session: Session = Depends(_get_session)
) -> User:
    user = get_user_by_token_(token, session=session)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"X-JWT-Action": '{"type":"DELETE","token":""}'},
        )

    return user


@router.post("/login")
def login(
        response: Response,
        body: LoginIn = Body(),
        session: Session = Depends(_get_session)
):
    token = login_(body.login, body.password, session=session)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    response.headers["X-JWT-Action"] = json.dumps({
        "type": "SAVE",
        "token": token
    })


@router.get("/me")
def me(user: User = Depends(get_user)):
    return {"id": user.id, "login": user.login, "cv": user.cv}


@router.post("/logout-all")
def logout_all(
        user: User = Depends(get_user),
        session: Session = Depends(_get_session),
):
    user.cv += 1
    session.commit()
    return {"ok": True, "cv": user.cv}


@router.get("/verify")
def verify(_: User = Depends(get_user)):
    return { "ok": True }