from datetime import datetime, date
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app import models, crud


# ---- App ----
app = FastAPI()

# Static + Templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---- DB dependency ----
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Helpers ----
def parse_date(date_str: str) -> date:
    # Accept: YYYY/MM/DD or YYYY-MM-DD
    s = (date_str or "").strip()
    if "/" in s:
        return datetime.strptime(s, "%Y/%m/%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def current_month_str() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


# ---- Routes ----
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # 兼容：crud.py 里可能叫 list_recent
    # 我们在 crud.py 里会补一个 list_records 的别名
    records = crud.list_records(db)

    # 首页顶部统计（可选，按你原来逻辑）
    totals = crud.month_totals(db, month=current_month_str())

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "records": records,
            "totals": totals,
            "default_date": date.today().strftime("%Y/%m/%d"),
        },
    )


@app.post("/add")
def add_record(
    r_type: str = Form(...),          # income / expense
    amount: float = Form(...),
    category: str = Form(...),
    date_str: str = Form(...),        # "2025/12/30" or "2025-12-30"
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    d = parse_date(date_str)

    crud.create_record(
        db=db,
        r_type=r_type.strip(),
        amount=float(amount),
        category=category.strip(),
        date=d,
        note=(note or "").strip(),
    )

    # 保存完回首页
    return RedirectResponse(url="/", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    month: Optional[str] = None,  # "YYYY-MM"
    db: Session = Depends(get_db),
):
    month = (month or "").strip() or current_month_str()

    totals = crud.month_totals(db, month=month)
    breakdown_expense = crud.month_category_breakdown(db, month=month, r_type="expense")
    breakdown_income = crud.month_category_breakdown(db, month=month, r_type="income")

    # 你如果统计页是“原来的月统计模式”，就用 month 参数即可切换月份
    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "month": month,
            "totals": totals,
            "breakdown_expense": breakdown_expense,
            "breakdown_income": breakdown_income,
        },
    )



