from datetime import datetime, date
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ✅ 正确的包内导入（关键）
from app.db import SessionLocal, engine
from app.models import Base, Record
from app import crud

app = FastAPI()

# 创建表
Base.metadata.create_all(bind=engine)

# 静态文件 & 模板
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---------- 工具函数 ----------

def _to_date_str(x: Any) -> str:
    if x is None:
        return date.today().strftime("%Y-%m-%d")
    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")
    s = str(x).strip().replace("/", "-")
    if len(s) == 7:
        return f"{s}-01"
    return s


def _parse_month(month: Optional[str]) -> str:
    if month:
        return month.strip()[:7]
    return date.today().strftime("%Y-%m")


def _normalize_payload(d: Dict[str, Any]) -> Dict[str, Any]:
    r_type = d.get("r_type") or d.get("type") or "expense"
    if r_type in ["支出", "expense"]:
        r_type = "expense"
    elif r_type in ["收入", "income"]:
        r_type = "income"

    try:
        amount = float(d.get("amount", 0))
    except Exception:
        amount = 0.0

    return {
        "r_type": r_type,
        "amount": amount,
        "category": str(d.get("category", "")).strip(),
        "date_str": _to_date_str(d.get("date_str") or d.get("date")),
        "note": str(d.get("note", "")).strip(),
    }


# ---------- 页面 ----------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    try:
        records = crud.list_records(db)
        total_expense = sum(r.amount for r in records if r.r_type == "expense")
        total_income = sum(r.amount for r in records if r.r_type == "income")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "records": records,
                "total_expense": total_expense,
                "total_income": total_income,
                "balance": total_income - total_expense,
            },
        )
    finally:
        db.close()


# 防止浏览器 GET /add 报错
@app.get("/add")
def add_redirect():
    return RedirectResponse("/", status_code=302)


# ---------- 新增记录（关键修复点） ----------

@app.post("/add")
async def add_record(
    request: Request,
    r_type: Optional[str] = Form(None),
    date_str: Optional[str] = Form(None),
    amount: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
):
    db = SessionLocal()
    try:
        payload = {}

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)

        # 合并表单参数
        payload.update({
            "r_type": r_type,
            "date_str": date_str,
            "amount": amount,
            "category": category,
            "note": note,
        })

        data = _normalize_payload(payload)

        crud.create_record(
            db,
            r_type=data["r_type"],
            amount=data["amount"],
            category=data["category"],
            date_str=data["date_str"],
            note=data["note"],
        )

        if "application/json" in content_type:
            return JSONResponse({"ok": True})

        return RedirectResponse("/", status_code=303)
    finally:
        db.close()


# ---------- 月统计 ----------

@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, month: Optional[str] = None):
    month = _parse_month(month)
    db = SessionLocal()
    try:
        records = crud.list_records_by_month(db, month)

        expense = sum(r.amount for r in records if r.r_type == "expense")
        income = sum(r.amount for r in records if r.r_type == "income")

        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "records": records,
                "month": month,
                "total_expense": expense,
                "total_income": income,
                "balance": income - expense,
            },
        )
    finally:
        db.close()


