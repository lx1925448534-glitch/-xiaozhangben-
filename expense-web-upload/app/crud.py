from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict, Optional, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import Record, User


# ---------- Users ----------
def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password_hash: str, phone: Optional[str] = None) -> User:
    u = User(username=username, password_hash=password_hash, phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------- Records ----------
def list_records(db: Session, user_id: int, limit: int = 200) -> List[Record]:
    return (
        db.query(Record)
        .filter(Record.user_id == user_id)
        .order_by(desc(Record.date), desc(Record.id))
        .limit(limit)
        .all()
    )


def create_record(
    db: Session,
    user_id: int,
    type_: str,
    amount: float,
    category: str,
    d: date,
    note: str = "",
) -> Record:
    obj = Record(
        user_id=user_id,
        type=type_,
        amount=float(amount),
        category=category,
        date=d,
        note=(note or None),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_record(db: Session, user_id: int, record_id: int) -> bool:
    obj = (
        db.query(Record)
        .filter(Record.id == record_id, Record.user_id == user_id)
        .first()
    )
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ---------- Time helpers ----------
def month_range(yyyy_mm: str) -> Tuple[date, date]:
    y, m = yyyy_mm.split("-")
    y, m = int(y), int(m)
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)
    return start, end


def week_range(yyyy_w: str) -> Tuple[date, date]:
    # input type="week" gives "YYYY-Www"
    y, w = yyyy_w.split("-W")
    y, w = int(y), int(w)
    start = date.fromisocalendar(y, w, 1)  # Monday
    end = date.fromisocalendar(y, w, 7)    # Sunday
    return start, end


# ---------- Aggregations ----------
def range_summary(db: Session, user_id: int, start: date, end: date) -> Dict[str, float]:
    rows = (
        db.query(Record.type, func.sum(Record.amount))
        .filter(Record.user_id == user_id, Record.date >= start, Record.date <= end)
        .group_by(Record.type)
        .all()
    )

    expense = 0.0
    income = 0.0
    for t, s in rows:
        if s is None:
            continue
        if t == "expense":
            expense = float(s)
        elif t == "income":
            income = float(s)

    return {
        "expense": round(expense, 2),
        "income": round(income, 2),
        "balance": round(income - expense, 2),
    }


def category_breakdown(db: Session, user_id: int, start: date, end: date, type_: str) -> List[Dict[str, Any]]:
    rows = (
        db.query(Record.category, func.sum(Record.amount).label("total"))
        .filter(
            Record.user_id == user_id,
            Record.type == type_,
            Record.date >= start,
            Record.date <= end,
        )
        .group_by(Record.category)
        .order_by(desc(func.sum(Record.amount)))
        .all()
    )
    return [{"category": (c or "未分类"), "total": float(t or 0.0)} for c, t in rows]
