from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from back.databases import main, User
from back.security import decode_token, verify_password, create_token, hash_password

auto_user_session = main.auto_session


@auto_user_session
def create_new_user_(login: str, password: str, session: Session = None) -> User | None:
    user = get_user_by_login_(login, session=session)
    if user is not None:
        return None

    user = User()
    user.cv = 0
    user.login = login
    user.password_hash = hash_password(password)

    session.add(user)
    session.flush()

    return user


@auto_user_session
def get_user_by_login_(login: str, session: Session = None) -> User | None:
    return session.execute(select(User).where(User.login == login)).scalar_one_or_none()


@auto_user_session
def get_user_by_uid_(uid: int, session: Session = None) -> User | None:
    return session.get(User, uid)


@auto_user_session
def get_user_by_token_(token: str, session: Session = None) -> User | None:
    try:
        data = decode_token(token)
    except PyJWTError, KeyError:
        return None
    else:
        uid = data["sub"]
        cv = data["cv"]

        user = get_user_by_uid_(uid, session=session)

        return None if user is None or cv != user.cv else user


@auto_user_session
def login_(login: str, password: str, session: Session = None) -> User | None:
    user = get_user_by_login_(login, session=session)

    if user is None:
        verify_password()
        return None

    # noinspection PyTypeChecker
    return create_token(user.id, user.cv) if verify_password(password, user.password_hash) else None
