from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    phone = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    records = relationship("Record", back_populates="user")


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    type = Column(String, nullable=False)       # "expense" or "income"
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    date = Column(Date, nullable=False)

    payment_method = Column(String, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="records")
