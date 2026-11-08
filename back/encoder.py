from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from back.databases import Encoding, encoding
from back.new_db import auto_session


class Encoder:
    auto_encoding_session = auto_session(encoding.with_session)

    @auto_encoding_session
    def encode(self, name: str, session: Session = None) -> int:
        id_ = session.scalar(select(Encoding.id).where(Encoding.name == name))
        if id_ is not None:
            return id_

        try:
            encoding = Encoding()
            encoding.name = name
            session.add(encoding)

            session.flush()

            # noinspection PyTypeChecker
            return encoding.id
        except IntegrityError:
            session.rollback()
            id_ = session.scalar(select(Encoding.id).where(Encoding.name == name))
            if id_ is not None:
                return id_
            raise

    @auto_encoding_session
    def decode(self, id_: int, session: Session = None) -> str | None:
        return session.scalar(select(Encoding.name).where(Encoding.id == id_))


encoder = Encoder()