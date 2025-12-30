from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, List
from datetime import date

from app import models


# 1) 兼容 main.py 旧调用：list_records -> list_recent
def list_records(db: Session):
    # 如果你原来就有 list_recent，就直接复用
    if hasattr(__import__("app.crud", fromlist=["x"]), "list_recent"):
        return list_recent(db)  # type: ignore[name-defined]
    # 否则就按时间倒序取全部
    return db.query(models.Record).order_by(models.Record.date.desc(), models.Record.id.desc()).all()


# 2) 创建记录（如果你原来已经有 create_record，就保留你自己的实现）
def create_record(db: Session, r_type: str, amount: float, category: str, date: date, note: str):
    obj = models.Record(
        r_type=r_type,
        amount=amount,
        category=category,
        date=date,
        note=note,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


# 3) 月统计 totals：收入/支出/结余
def month_totals(db: Session, month: str) -> Dict[str, float]:
    # month: "YYYY-MM"
    y, m = month.split("-")
    y, m = int(y), int(m)

    # SQLite / Postgres 通用：用 year/month 提取（不同DB略不同）
    # 这里用字符串前缀匹配最稳：把 date 转成 YYYY-MM
    month_prefix = f"{y:04d}-{m:02d}"

    q = db.query(models.Record.r_type, func.sum(models.Record.amount)) \
        .filter(func.to_char(models.Record.date, "YYYY-MM") == month_prefix) \
        .group_by(models.Record.r_type)

    sums = {"expense": 0.0, "income": 0.0}
    for r_type, s in q.all():
        if r_type in sums and s is not None:
            sums[r_type] = float(s)

    return {
        "month": month_prefix,
        "total_expense": sums["expense"],
        "total_income": sums["income"],
        "balance": sums["income"] - sums["expense"],
    }


# 4) 月度分类占比：用于饼图（支出/收入分别一张）
def month_category_breakdown(db: Session, month: str, r_type: str) -> List[Dict[str, float]]:
    y, m = month.split("-")
    month_prefix = f"{int(y):04d}-{int(m):02d}"

    q = db.query(models.Record.category, func.sum(models.Record.amount).label("total")) \
        .filter(models.Record.r_type == r_type) \
        .filter(func.to_char(models.Record.date, "YYYY-MM") == month_prefix) \
        .group_by(models.Record.category) \
        .order_by(func.sum(models.Record.amount).desc())

    out = []
    for cat, total in q.all():
        out.append({"category": cat, "total": float(total or 0)})
    return out
