from sqlalchemy import select

from back.db import get_session_cm
from back.models import TitleRecord


def title_to_id(title: str) -> int:
    with get_session_cm() as session:
        record: TitleRecord|None = session.execute(select(TitleRecord).where(TitleRecord.title == title)).scalar_one_or_none()
        if record is None:
            new_record = TitleRecord(title=title)
            session.add(new_record)
            session.commit()
            # noinspection PyTypeChecker
            return int(new_record.id)
        # noinspection PyTypeChecker
        return int(record.id)


def id_to_title(_id: int) -> str|None:
    with get_session_cm() as session:
        record = session.get(TitleRecord, _id)
        return None if record is None else record.id


def get_sources(title: str) -> list[str] | None:
    pass


def get_ordinals(title: str, source_title:str) -> list[int]|None:
    pass