from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Literal, Dict, Any, List

from fastapi import FastAPI, Request, Body, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, Date, Numeric, func
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    # Fallback for local dev; Render will provide DATABASE_URL if you created a Postgres on Render.
    DATABASE_URL = "sqlite:///./app.db"

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    r_type = Column(String(16), nullable=False)     # "income" / "expense"
    category = Column(String(64), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    date = Column(Date, nullable=False)
    note = Column(String(255), nullable=True)


Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def parse_date_str(date_str: str) -> date:
    # Accept "YYYY-MM-DD" or "YYYY/MM/DD"
    s = date_str.strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d").date()


def month_range(month: str) -> tuple[date, date]:
    # month: "YYYY-MM"
    m = month.strip()
    if len(m) != 7 or m[4] != "-":
        raise ValueError("month must be YYYY-MM")
    y = int(m[:4])
    mo = int(m[5:7])
    start = date(y, mo, 1)
    if mo == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, mo + 1, 1)
    return start, end


def monthly_stats(db, month: str) -> Dict[str, Any]:
    start, end = month_range(month)

    income_sum = db.query(func.coalesce(func.sum(Record.amount), 0)).filter(
        Record.r_type == "income",
        Record.date >= start,
        Record.date < end,
    ).scalar()

    expense_sum = db.query(func.coalesce(func.sum(Record.amount), 0)).filter(
        Record.r_type == "expense",
        Record.date >= start,
        Record.date < end,
    ).scalar()

    by_category_rows = db.query(
        Record.r_type,
        Record.category,
        func.coalesce(func.sum(Record.amount), 0).label("total"),
    ).filter(
        Record.date >= start,
        Record.date < end,
    ).group_by(
        Record.r_type, Record.category
    ).order_by(
        Record.r_type, func.sum(Record.amount).desc()
    ).all()

    by_category: Dict[str, List[Dict[str, Any]]] = {"income": [], "expense": []}
    for r_type, category, total in by_category_rows:
        key = (r_type or "").strip()
        if key not in by_category:
            continue
        by_category[key].append({"category": category, "total": float(total)})

    return {
        "month": month,
        "total_income": float(income_sum),
        "total_expense": float(expense_sum),
        "balance": float(income_sum) - float(expense_sum),
        "by_category": by_category,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    return templates.TemplateResponse("stats.html", {"request": request})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/records")
def list_records(month: Optional[str] = Query(default=None)):
    db = SessionLocal()
    try:
        q = db.query(Record).order_by(Record.date.desc(), Record.id.desc())
        if month:
            start, end = month_range(month)
            q = q.filter(Record.date >= start, Record.date < end)

        rows = q.limit(500).all()
        return [
            {
                "id": r.id,
                "r_type": r.r_type,
                "category": r.category,
                "amount": float(r.amount),
                "date": r.date.isoformat(),
                "note": r.note or "",
            }
            for r in rows
        ]
    finally:
        db.close()


@app.post("/api/records")
def create_record(payload: Dict[str, Any] = Body(...)):
    r_type = (payload.get("r_type") or "").strip()
    category = (payload.get("category") or "").strip()
    amount = payload.get("amount")
    date_str = (payload.get("date") or payload.get("date_str") or "").strip()
    note = (payload.get("note") or "").strip()

    if r_type not in ("income", "expense"):
        raise HTTPException(status_code=400, detail="r_type must be income or expense")
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    if amount is None:
        raise HTTPException(status_code=400, detail="amount is required")
    try:
        amount_val = float(amount)
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be a number")
    if not date_str:
        raise HTTPException(status_code=400, detail="date is required")

    try:
        d = parse_date_str(date_str)
    except Exception:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    db = SessionLocal()
    try:
        r = Record(r_type=r_type, category=category, amount=amount_val, date=d, note=note or None)
        db.add(r)
        db.commit()
        db.refresh(r)
        return {"ok": True, "id": r.id}
    finally:
        db.close()


@app.post("/api/records/{record_id}/delete")
def delete_record(record_id: int):
    db = SessionLocal()
    try:
        r = db.query(Record).filter(Record.id == record_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="record not found")
        db.delete(r)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# ---- Monthly stats (your original requirement) ----
@app.get("/api/stats/monthly")
def stats_monthly(month: str = Query(..., description="YYYY-MM")):
    db = SessionLocal()
    try:
        return monthly_stats(db, month)
    finally:
        db.close()


# ---- Backward compatible endpoint to avoid 422 ----
# If your front-end still calls /api/stats with r_type + date_str, it won't crash.
@app.get("/api/stats")
def stats_get(
    r_type: Optional[str] = Query(default=None),
    date_str: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None),
):
    db = SessionLocal()
    try:
        if month:
            return monthly_stats(db, month)

        if date_str:
            d = parse_date_str(date_str)
            m = f"{d.year:04d}-{d.month:02d}"
            return monthly_stats(db, m)

        # If nothing provided, default to current month
        today = date.today()
        m = f"{today.year:04d}-{today.month:02d}"
        return monthly_stats(db, m)
    finally:
        db.close()


@app.post("/api/stats")
def stats_post(payload: Dict[str, Any] = Body(...)):
    # Accept { "month": "YYYY-MM" } OR { "date_str": "YYYY-MM-DD" } (old)
    month = (payload.get("month") or "").strip()
    date_str = (payload.get("date_str") or "").strip()

    db = SessionLocal()
    try:
        if month:
            return monthly_stats(db, month)
        if date_str:
            d = parse_date_str(date_str)
            m = f"{d.year:04d}-{d.month:02d}"
            return monthly_stats(db, m)

        today = date.today()
        m = f"{today.year:04d}-{today.month:02d}"
        return monthly_stats(db, m)
    finally:
        db.close()



