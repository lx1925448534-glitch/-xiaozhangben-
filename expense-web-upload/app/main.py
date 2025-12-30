from datetime import datetime, date
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Your project modules (keep these imports)
from db import SessionLocal, engine
from models import Base, Record  # Record model should exist
import crud  # should provide create/get/list/delete/update etc.

app = FastAPI()

# Create tables (safe to call)
Base.metadata.create_all(bind=engine)

# Static + templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _to_date_str(x: Any) -> str:
    """
    Normalize date input to YYYY-MM-DD string.
    Accepts 'YYYY-MM-DD', 'YYYY/MM/DD', datetime/date.
    """
    if x is None:
        return date.today().strftime("%Y-%m-%d")
    if isinstance(x, (datetime, date)):
        return x.strftime("%Y-%m-%d")
    s = str(x).strip()
    if not s:
        return date.today().strftime("%Y-%m-%d")
    s = s.replace("/", "-")
    # If user passes YYYY-MM, we take first day of month
    if len(s) == 7:
        return f"{s}-01"
    return s


def _parse_month(month_str: Optional[str]) -> str:
    """
    Return YYYY-MM, default current month.
    """
    if month_str:
        m = month_str.strip().replace("/", "-")
        if len(m) >= 7:
            return m[:7]
    return date.today().strftime("%Y-%m")


def _normalize_payload(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept multiple possible field names from frontend and normalize:
      r_type: 'expense'/'income' or '支出'/'收入' etc.
      amount: float
      category: str
      date_str: 'YYYY-MM-DD'
      note: str
    """
    # r_type
    r_type = d.get("r_type") or d.get("type") or d.get("record_type") or d.get("rtype")
    if r_type is None:
        r_type = "expense"
    r_type = str(r_type).strip()

    # Map Chinese/variants to backend values
    # You can adjust if your DB expects '支出/收入' instead of 'expense/income'
    if r_type in ["支出", "expense", "out", "pay", "0", "EXPENSE"]:
        r_type_norm = "expense"
    elif r_type in ["收入", "income", "in", "earn", "1", "INCOME"]:
        r_type_norm = "income"
    else:
        # fallback: keep raw
        r_type_norm = r_type

    # amount
    amount_raw = d.get("amount")
    if amount_raw is None:
        amount_raw = d.get("money")
    if amount_raw is None:
        amount_raw = d.get("amt")
    try:
        amount = float(str(amount_raw).strip())
    except Exception:
        amount = 0.0

    # category
    category = d.get("category") or d.get("cate") or d.get("c") or ""
    category = str(category).strip()

    # date_str
    date_raw = d.get("date_str") or d.get("date") or d.get("day")
    date_str = _to_date_str(date_raw)

    # note
    note = d.get("note") or d.get("remark") or d.get("memo") or ""
    note = str(note).strip()

    return {
        "r_type": r_type_norm,
        "amount": amount,
        "category": category,
        "date_str": date_str,
        "note": note,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    db = SessionLocal()
    try:
        # Expect crud.list_records returns list[Record]
        records = crud.list_records(db)
        # Totals
        total_expense = sum(r.amount for r in records if getattr(r, "r_type", "") == "expense")
        total_income = sum(r.amount for r in records if getattr(r, "r_type", "") == "income")
        balance = total_income - total_expense
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "records": records,
                "total_expense": round(total_expense, 2),
                "total_income": round(total_income, 2),
                "balance": round(balance, 2),
            },
        )
    finally:
        db.close()


# IMPORTANT:
# If someone opens /add in browser, redirect to home instead of 422
@app.get("/add")
def add_get_redirect():
    return RedirectResponse(url="/", status_code=302)


@app.post("/add")
async def add_record(
    request: Request,
    # Make all optional so FastAPI won't throw 422 before we normalize
    r_type: Optional[str] = Form(default=None),
    date_str: Optional[str] = Form(default=None),
    amount: Optional[str] = Form(default=None),
    category: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
):
    """
    Compatible with:
      - HTML form submit (application/x-www-form-urlencoded or multipart/form-data)
      - fetch JSON (application/json)
    And compatible with multiple field names from frontend.
    """
    db = SessionLocal()
    try:
        content_type = request.headers.get("content-type", "").lower()

        payload: Dict[str, Any] = {}

        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                payload = {}
        else:
            # Try form first
            try:
                form = await request.form()
                payload = dict(form)
            except Exception:
                payload = {}

        # Merge explicit params (if present)
        # This helps if your form uses correct names sometimes
        if r_type is not None:
            payload["r_type"] = r_type
        if date_str is not None:
            payload["date_str"] = date_str
        if amount is not None:
            payload["amount"] = amount
        if category is not None:
            payload["category"] = category
        if note is not None:
            payload["note"] = note

        normalized = _normalize_payload(payload)

        # Create record (prefer your crud.create_record)
        # Expected fields in DB/Record: r_type, date_str, amount, category, note
        crud.create_record(
            db,
            r_type=normalized["r_type"],
            date_str=normalized["date_str"],
            amount=normalized["amount"],
            category=normalized["category"],
            note=normalized["note"],
        )

        # If request is JSON, return JSON
        if "application/json" in content_type:
            return JSONResponse({"ok": True})

        # Otherwise redirect back to home UI
        return RedirectResponse(url="/", status_code=303)

    finally:
        db.close()


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, month: Optional[str] = None):
    """
    Monthly stats view: /stats?month=YYYY-MM
    Default: current month.
    """
    target_month = _parse_month(month)
    db = SessionLocal()
    try:
        records = crud.list_records_by_month(db, target_month)

        total_expense = sum(r.amount for r in records if getattr(r, "r_type", "") == "expense")
        total_income = sum(r.amount for r in records if getattr(r, "r_type", "") == "income")
        balance = total_income - total_expense

        # category breakdown
        cat_expense: Dict[str, float] = {}
        cat_income: Dict[str, float] = {}
        for r in records:
            cat = (getattr(r, "category", "") or "").strip() or "未分类"
            if getattr(r, "r_type", "") == "expense":
                cat_expense[cat] = cat_expense.get(cat, 0.0) + float(r.amount)
            elif getattr(r, "r_type", "") == "income":
                cat_income[cat] = cat_income.get(cat, 0.0) + float(r.amount)

        # sort
        cat_expense_sorted = sorted(cat_expense.items(), key=lambda x: x[1], reverse=True)
        cat_income_sorted = sorted(cat_income.items(), key=lambda x: x[1], reverse=True)

        return templates.TemplateResponse(
            "stats.html",
            {
                "request": request,
                "month": target_month,
                "records": records,
                "total_expense": round(total_expense, 2),
                "total_income": round(total_income, 2),
                "balance": round(balance, 2),
                "cat_expense": cat_expense_sorted,
                "cat_income": cat_income_sorted,
            },
        )
    finally:
        db.close()
