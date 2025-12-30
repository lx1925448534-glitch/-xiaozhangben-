from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Any, Dict

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ✅ 关键：在 Render 上必须用包导入（别再用 from db import ...）
from app.db import SessionLocal, engine
from app import models, crud

app = FastAPI()

# Create tables (safe)
models.Base.metadata.create_all(bind=engine)

# Static + templates（保持你现有目录结构不变）
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _today_yyyy_mm() -> str:
    t = date.today()
    return f"{t.year:04d}-{t.month:02d}"


def _parse_date_any(s: str) -> date:
    """
    Accept:
      - YYYY-MM-DD
      - YYYY/MM/DD
    """
    ss = (s or "").strip().replace("/", "-")
    return datetime.strptime(ss, "%Y-%m-%d").date()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    try:
        # ✅ 这里不会再炸：crud.py 里保证有 list_records()
        records = crud.list_records(db)

        # 主页顶部总览（本月）
        totals = crud.month_totals(db, _today_yyyy_mm())

        # 兼容不同模板写法：既给 totals，也给拆开的字段
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "records": records,
                "totals": totals,
                "total_expense": totals["total_expense"],
                "total_income": totals["total_income"],
                "balance": totals["balance"],
                "default_date": date.today().strftime("%Y/%m/%d"),
            },
        )
    finally:
        db.close()


# ✅ 防止你手动打开 /add 时出现 422/Field required
@app.get("/add")
def add_get_redirect():
    return RedirectResponse(url="/", status_code=302)


@app.post("/add")
def add_post(
    # ✅ 用 Form(...) 接收网页表单提交，彻底解决 Field required
    r_type: str = Form(...),        # expense / income（或 支出/收入 也行）
    amount: float = Form(...),
    category: str = Form(...),
    date_str: str = Form(...),      # 你现在表单里就是 date_str（截图报错就是缺它）
    note: str = Form(""),
):
    db = SessionLocal()
    try:
        # 兼容你前端可能传 支出/收入
        rt = (r_type or "").strip()
        if rt in ("支出", "expense"):
            rt = "expense"
        elif rt in ("收入", "income"):
            rt = "income"

        d = _parse_date_any(date_str)

        crud.create_record(
            db=db,
            r_type=rt,
            amount=float(amount),
            category=(category or "").strip(),
            date_value=d,
            date_str=(date_str or "").strip(),
            note=(note or "").strip(),
        )
    finally:
        db.close()

    return RedirectResponse(url="/", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, month: Optional[str] = None):
    """
    月统计模式：
      /stats?month=YYYY-MM
    不传 month 默认本月
    """
    m = (month or "").strip()[:7] or _today_yyyy_mm()

    db = SessionLocal()
    try:
        totals = crud.month_totals(db, m)
        breakdown_expense = crud.month_category_breakdown(db, m, "expense")
        breakdown_income = crud.month_category_breakdown(db, m, "income")

        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "month": m,
                "totals": totals,
                "total_expense": totals["total_expense"],
                "total_income": totals["total_income"],
                "balance": totals["balance"],
                "breakdown_expense": breakdown_expense,
                "breakdown_income": breakdown_income,
            },
        )
    finally:
        db.close()


# （可选）健康检查，方便你验证 Render 是否真启动
@app.get("/health")
def health():
    return JSONResponse({"ok": True})
