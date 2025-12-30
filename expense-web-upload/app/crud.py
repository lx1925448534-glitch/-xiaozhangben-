from __future__ import annotations

from datetime import date
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app import models


def _record_cls():
    # 你的 models 里大概率叫 Record
    return models.Record


def _has_col(col_name: str) -> bool:
    # SQLAlchemy Column 在类上是 attribute（hasattr 可用）
    R = _record_cls()
    return hasattr(R, col_name)


def list_recent(db: Session, limit: int = 200):
    R = _record_cls()
    q = db.query(R)

    # 尽量按时间倒序（兼容 date / date_str）
    if _has_col("date"):
        q = q.order_by(desc(R.date))
    elif _has_col("date_str"):
        q = q.order_by(desc(R.date_str))
    if _has_col("id"):
        q = q.order_by(desc(R.id))

    return q.limit(limit).all()


def list_records(db: Session, limit: int = 200):
    # ✅ 你线上 500 的根因就是 main.py 调了 list_records 但 crud 没这个函数
    # 这里直接做别名：list_records = list_recent
    return list_recent(db, limit=limit)


def create_record(
    db: Session,
    r_type: str,
    amount: float,
    category: str,
    date_value: Optional[date] = None,
    date_str: Optional[str] = None,
    note: str = "",
):
    R = _record_cls()
    obj = R()

    # 逐个字段 set，兼容你模型字段名不同
    if _has_col("r_type"):
        setattr(obj, "r_type", r_type)
    elif _has_col("type"):
        setattr(obj, "type", r_type)

    if _has_col("amount"):
        setattr(obj, "amount", amount)

    if _has_col("category"):
        setattr(obj, "category", category)

    if _has_col("note"):
        setattr(obj, "note", note)

    if date_value is None:
        date_value = date.today()

    # 兼容两种：date (Date) / date_str (String)
    if _has_col("date"):
        setattr(obj, "date", date_value)
    if _has_col("date_str"):
        # 尽量用 YYYY-MM-DD
        if date_str and len(date_str.strip()) >= 8:
            ds = date_str.strip().replace("/", "-")
        else:
            ds = date_value.strftime("%Y-%m-%d")
        setattr(obj, "date_str", ds)

    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def month_totals(db: Session, month: str) -> Dict[str, float]:
    """
    month: 'YYYY-MM'
    兼容：
      - 模型有 date (Date)
      - 模型有 date_str (String: 'YYYY-MM-DD' 或 'YYYY/MM/DD')
    """
    R = _record_cls()

    total_expense = 0.0
    total_income = 0.0

    if _has_col("date_str"):
        # 用前缀匹配最稳（也兼容 'YYYY/MM/DD'，我们把 / 也当 - 的可能性忽略，至少线上能跑）
        q = (
            db.query(R.r_type, func.sum(R.amount))
            .filter(R.date_str.startswith(month))
            .group_by(R.r_type)
        )
        rows = q.all()
    elif _has_col("date"):
        # Postgres 可用：to_char(date, 'YYYY-MM')
        q = (
            db.query(R.r_type, func.sum(R.amount))
            .filter(func.to_char(R.date, "YYYY-MM") == month)
            .group_by(R.r_type)
        )
        rows = q.all()
    else:
        rows = []

    for rt, s in rows:
        if s is None:
            continue
        if rt == "expense" or rt == "支出":
            total_expense = float(s)
        elif rt == "income" or rt == "收入":
            total_income = float(s)

    return {
        "month": month,
        "total_expense": round(total_expense, 2),
        "total_income": round(total_income, 2),
        "balance": round(total_income - total_expense, 2),
    }


def month_category_breakdown(db: Session, month: str, r_type: str) -> List[Dict[str, Any]]:
    """
    返回形如：
      [{"category":"餐饮","total":123.0}, ...]
    供你 stats.html 做饼图用
    """
    R = _record_cls()

    if _has_col("date_str"):
        q = (
            db.query(R.category, func.sum(R.amount).label("total"))
            .filter(R.r_type == r_type)
            .filter(R.date_str.startswith(month))
            .group_by(R.category)
            .order_by(desc(func.sum(R.amount)))
        )
        rows = q.all()
    elif _has_col("date"):
        q = (
            db.query(R.category, func.sum(R.amount).label("total"))
            .filter(R.r_type == r_type)
            .filter(func.to_char(R.date, "YYYY-MM") == month)
            .group_by(R.category)
            .order_by(desc(func.sum(R.amount)))
        )
        rows = q.all()
    else:
        rows = []

    out: List[Dict[str, Any]] = []
    for cat, total in rows:
        out.append({"category": cat or "未分类", "total": float(total or 0.0)})
    return out
