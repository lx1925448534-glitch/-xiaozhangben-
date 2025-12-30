from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import SessionLocal, engine
from app.db import Base
from app import models, crud

app = FastAPI()

# Create tables on startup (safe)
Base.metadata.create_all(bind=engine)

# static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _parse_date_any(s: str) -> date:
    ss = (s or "").strip().replace("/", "-")
    return datetime.strptime(ss, "%Y-%m-%d").date()


@app.get("/health")
def health():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    try:
        records = crud.list_records(db, limit=200)

        # 首页顶部：本月统计（用 DB 现有数据计算，简单稳）
        today = date.today()
        month_start = date(today.year, today.month, 1)

        exp = 0.0
        inc = 0.0
        for r in records:
            if month_start <= r.date <= today:
                if r.type == "expense":
                    exp += r.amount
                elif r.type == "income":
                    inc += r.amount

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "records": records,
                "total_expense": f"{exp:.2f}",
                "total_income": f"{inc:.2f}",
                "balance": f"{(inc - exp):.2f}",
            },
        )
    finally:
        db.close()


# 防止 GET /add 被打开时报错（表单只走 POST）
@app.get("/add")
def add_get_redirect():
    return RedirectResponse(url="/", status_code=302)


@app.post("/add")
def add_post(
    # ✅ 必须对齐 index.html：name="type/amount/category/date/note"
    type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    note: str = Form(""),
):
    t = (type or "").strip()
    if t not in ("expense", "income"):
        t = "expense"

    d = _parse_date_any(date)

    db = SessionLocal()
    try:
        crud.create_record(
            db=db,
            type_=t,
            amount=float(amount),
            category=(category or "").strip(),
            d=d,
            note=(note or "").strip(),
        )
    finally:
        db.close()

    return RedirectResponse(url="/", status_code=303)


# ✅ 对齐 index.html 删除按钮 action="/delete/{{ r.id }}"
@app.post("/delete/{record_id}")
def delete_post(record_id: int):
    db = SessionLocal()
    try:
        crud.delete_record(db, record_id)
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None, alias="to"),
):
    db = SessionLocal()
    try:
        start_d = _parse_date_any(from_) if from_ else None
        end_d = _parse_date_any(to) if to else None

        summary = crud.range_summary(db, start_d, end_d)
        lines = crud.week_lines(db, start_d, end_d)

        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "date_from": from_ or "",
                "date_to": to or "",
                "range_expense": f"{summary['range_expense']:.2f}",
                "range_income": f"{summary['range_income']:.2f}",
                "range_balance": f"{summary['range_balance']:.2f}",
                "week_lines": lines,
            },
        )
    finally:
        db.close()
