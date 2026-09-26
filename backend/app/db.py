from sqlalchemy import create_engine
from pathlib import Path
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def make_engine(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite:///") and ":memory:" not in url:
        db_file = url.removeprefix("sqlite:///")
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)

def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
