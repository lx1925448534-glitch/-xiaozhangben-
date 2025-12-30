from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date
from app.models import Record

EXPENSE_CATEGORIES = [
    "餐饮", "交通", "购物", "房租", "娱乐", "医疗", "学习", "其他"
]

INCOME_CATEGORIES = [
    "工资", "红包", "其他"
]


def add_record(
    db: Session,
    r_type: str,
    amount: float,
    category: str,
    r_date: date,
    note: str | None,
) -> None:
    rec = Record(
        type=r_type,
        amount=amount,
        category=category,
        date=r_date,
        payment_method=None,   # 不再使用
        note=note,
    )
    db.add(rec)
    db.commit()


def delete_record(db: Session, record_id: int) -> None:
    rec = db.query(Record).filter(Record.id == record_id).first()
    if rec:
        db.delete(rec)
        db.commit()


def list_recent(db: Session, limit: int = 50):
    return (
        db.query(Record)
        .order_by(Record.date.desc(), Record.id.desc())
        .limit(limit)
        .all()
    )


def summary_totals(db: Session):
    total_expense = (
        db.query(func.coalesce(func.sum(Record.amount), 0.0))
        .filter(Record.type == "expense")
        .scalar()
    )
    total_income = (
        db.query(func.coalesce(func.sum(Record.amount), 0.0))
        .filter(Record.type == "income")
        .scalar()
    )
    balance = float(total_income) - float(total_expense)
    return float(total_expense), float(total_income), float(balance)


def summary_by_category(db: Session):
    rows = (
        db.query(Record.category, func.sum(Record.amount))
        .filter(Record.type == "expense")
        .group_by(Record.category)
        .order_by(func.sum(Record.amount).desc())
        .all()
    )
    return [(c, float(s)) for c, s in rows]


def summary_totals_range(db: Session, start_date: date, end_date: date):
    q = db.query(Record).filter(and_(Record.date >= start_date, Record.date <= end_date))

    total_expense = (
        q.filter(Record.type == "expense")
        .with_entities(func.coalesce(func.sum(Record.amount), 0.0))
        .scalar()
    )
    total_income = (
        q.filter(Record.type == "income")
        .with_entities(func.coalesce(func.sum(Record.amount), 0.0))
        .scalar()
    )
    balance = float(total_income) - float(total_expense)
    return float(total_expense), float(total_income), float(balance)


def summary_by_category_range(db: Session, start_date: date, end_date: date):
    rows = (
        db.query(Record.category, func.sum(Record.amount))
        .filter(Record.type == "expense")
        .filter(and_(Record.date >= start_date, Record.date <= end_date))
        .group_by(Record.category)
        .order_by(func.sum(Record.amount).desc())
        .all()
    )
    return [(c, float(s)) for c, s in rows]
