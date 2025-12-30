from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import Record


def list_records(db: Session, limit: int = 200) -> List[Record]:
    return (
        db.query(Record)
        .order_by(desc(Record.date), desc(Record.id))
        .limit(limit)
        .all()
    )


def create_record(
    db: Session,
    type_: str,
    amount: float,
    category: str,
    d: date,
    note: str = "",
) -> Record:
    obj = Record(
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


def delete_record(db: Session, record_id: int) -> bool:
    obj = db.query(Record).filter(Record.id == record_id).first()
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def range_summary(db: Session, start: Optional[date], end: Optional[date]) -> Dict[str, float]:
    if not start or not end:
        return {"range_expense": 0.0, "range_income": 0.0, "range_balance": 0.0}

    rows = (
        db.query(Record.type, func.sum(Record.amount))
        .filter(Record.date >= start, Record.date <= end)
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
        "range_expense": round(expense, 2),
        "range_income": round(income, 2),
        "range_balance": round(income - expense, 2),
    }


def _week_start(d: date) -> date:
    # Monday as start of week
    return d - timedelta(days=d.weekday())


def week_lines(db: Session, start: Optional[date], end: Optional[date]) -> List[str]:
    if not start or not end:
        return []

    records = (
        db.query(Record)
        .filter(Record.date >= start, Record.date <= end)
        .order_by(Record.date.asc(), Record.id.asc())
        .all()
    )
    if not records:
        return []

    buckets: Dict[date, List[Record]] = {}
    for r in records:
        ws = _week_start(r.date)
        buckets.setdefault(ws, []).append(r)

    out: List[str] = []
    for ws in sorted(buckets.keys()):
        we = ws + timedelta(days=6)
        exp = sum(x.amount for x in buckets[ws] if x.type == "expense")
        inc = sum(x.amount for x in buckets[ws] if x.type == "income")
        bal = inc - exp
        out.append(
            f"{ws.strftime('%Y-%m-%d')} ~ {we.strftime('%Y-%m-%d')}：支出 ¥{exp:.2f}，收入 ¥{inc:.2f}，结余 ¥{bal:.2f}"
        )
    return out

