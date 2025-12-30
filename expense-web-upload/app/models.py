from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, Date, DateTime

from app.db import Base

class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)

    # 对齐你前端：type = expense / income
    type = Column(String, nullable=False)       # "expense" or "income"
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    date = Column(Date, nullable=False)

    # 前端暂时没用支付方式，但留着也不影响
    payment_method = Column(String, nullable=True)

    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
