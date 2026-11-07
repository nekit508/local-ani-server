from sqlalchemy import String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from back.new_db import DB


class Encoder:
    db: DB

    def __init__(self):
        self.db = DB(".db/encoders.db")

        class Encoding(self.db.Base):
            __tablename__ = "encoding"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(256), unique=True, index=True)

        self.Encoding = Encoding

    def encode(self, name: str) -> int:
        with self.db.with_session() as session:
            id_ = session.scalar(select(self.Encoding.id).where(self.Encoding.name == name))
            if id_ is not None:
                return id_

            try:
                encoding = self.Encoding()
                encoding.name = name
                session.add(encoding)

                session.flush()

                # noinspection PyTypeChecker
                return encoding.id
            except IntegrityError:
                session.rollback()
                id_ = session.scalar(select(self.Encoding.id).where(self.Encoding.name == name))
                if id_ is not None:
                    return id_
                raise

    def decode(self, id_: int) -> str | None:
        with self.db.with_session() as session:
            return session.scalar(select(self.Encoding.name).where(self.Encoding.id == id_))


encoder = Encoder()