# expense-web-upload/app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

def _normalize_database_url(url: str) -> str:
    # Render 常给 postgres://，SQLAlchemy 需要 postgresql:// 或带 driver
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    # 有些人手动配 postgresql://，也统一成 psycopg 驱动
    if url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
DATABASE_URL = _normalize_database_url(DATABASE_URL)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
