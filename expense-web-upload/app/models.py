# expense-web-upload/app/models.py
from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import relationship
from .db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    records = relationship("Record", back_populates="user", cascade="all, delete-orphan")

class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # r_type: "expense" / "income"
    r_type = Column(String(10), nullable=False, index=True)

    # 分类（品类）
    category = Column(String(50), nullable=False, default="其他")

    amount = Column(Numeric(12, 2), nullable=False)
    note = Column(String(200), nullable=True)

    # 记账日期
    r_date = Column(Date, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="records")

