# expense-web-upload/app/main.py
import os
from datetime import datetime, date
from pathlib import Path
from decimal import Decimal

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from passlib.context import CryptContext

from .db import SessionLocal, engine
from .models import User, Record
from .models import User, Record
from .db import Base

# ---------- App ----------
app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------- DB ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    # 自动建表（防止你第一次就 500）
    Base.metadata.create_all(bind=engine)


# ---------- Helpers ----------
def get_or_create_demo_user(db: Session) -> User:
    u = db.execute(select(User).where(User.username == "demo")).scalar_one_or_none()
    if u:
        return u
    demo = User(username="demo", password_hash=pwd_context.hash("demo123456"))
    db.add(demo)
    db.commit()
    db.refresh(demo)
    return demo


def parse_date_str(s: str) -> date:
    # 接受 YYYY-MM-DD
    return datetime.strptime(s, "%Y-%m-%d").date()


# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True}


# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_or_create_demo_user(db)

    rows = db.execute(
        select(Record)
        .where(Record.user_id == user.id)
        .order_by(Record.r_date.desc(), Record.id.desc())
        .limit(200)
    ).scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "records": rows, "username": user.username},
    )


@app.get("/add", response_class=HTMLResponse)
def add_page(request: Request):
    # 你如果没有 add.html，就继续用 index.html 里表单也行
    # 这里给个简单兜底页面：直接重定向回首页
    return RedirectResponse(url="/", status_code=303)


@app.post("/add")
def add_record(
    r_type: str = Form(...),
    date_str: str = Form(...),
    amount: str = Form(...),
    category: str = Form("其他"),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_or_create_demo_user(db)

    r_type = r_type.strip().lower()
    if r_type not in ("expense", "income"):
        raise HTTPException(status_code=400, detail="r_type must be expense or income")

    try:
        r_date = parse_date_str(date_str.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="date_str must be YYYY-MM-DD")

    try:
        amt = Decimal(amount.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="amount must be a number")

    category = (category or "其他").strip()[:50]
    note = (note or "").strip()[:200]

    rec = Record(
        user_id=user.id,
        r_type=r_type,
        r_date=r_date,
        amount=amt,
        category=category,
        note=note,
    )
    db.add(rec)
    db.commit()

    return RedirectResponse(url="/", status_code=303)


# ---------- Simple stats (先兜底，后面你要月/周我再按你的页面结构接上) ----------
@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db)):
    user = get_or_create_demo_user(db)

    # 按月聚合
    # Postgres: date_trunc('month', r_date)
    month_bucket = func.date_trunc("month", Record.r_date).label("bucket")

    rows = db.execute(
        select(
            month_bucket,
            Record.r_type,
            func.coalesce(func.sum(Record.amount), 0).label("total"),
        )
        .where(Record.user_id == user.id)
        .group_by(month_bucket, Record.r_type)
        .order_by(month_bucket.desc(), Record.r_type)
    ).all()

    return templates.TemplateResponse(
        "stats.html",
        {"request": request, "rows": rows, "username": user.username},
    )


# ---------- Better error visibility ----------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Render 上你看到 Internal Server Error，这里让你至少能看到更明确的错误
    # 生产环境你可以改成隐藏细节
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )


