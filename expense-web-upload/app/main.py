from datetime import datetime, date, timedelta
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import Base, engine, SessionLocal
from app import crud

app = FastAPI()
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)


def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def parse_month_str(s: str) -> tuple[int, int] | None:
    # "YYYY-MM"
    try:
        parts = s.split("-")
        if len(parts) != 2:
            return None
        y = int(parts[0])
        m = int(parts[1])
        if m < 1 or m > 12:
            return None
        return y, m
    except Exception:
        return None


def month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    end = next_month - timedelta(days=1)
    return start, end


def month_weeks_full(y: int, m: int) -> list[tuple[date, date]]:
    # full weeks Monday-Sunday
    m_start, m_end = month_range(y, m)
    first_monday = m_start - timedelta(days=m_start.weekday())
    last_sunday = m_end + timedelta(days=(6 - m_end.weekday()))

    weeks = []
    cur = first_monday
    while cur <= last_sunday:
        weeks.append((cur, cur + timedelta(days=6)))
        cur += timedelta(days=7)
    return weeks


def build_home_data():
    db = SessionLocal()
    try:
        records = crud.list_recent(db, limit=50)
        total_expense, total_income, balance = crud.summary_totals(db)
        by_category = crud.summary_by_category(db)
    finally:
        db.close()

    return {
        "records": records,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": balance,
        "by_category": by_category,
        "expense_categories": crud.EXPENSE_CATEGORIES,
        "income_categories": crud.INCOME_CATEGORIES,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    data = build_home_data()
    return templates.TemplateResponse("index.html", {"request": request, **data})


@app.post("/add")
def add(
    r_type: str = Form(...),
    amount: str = Form(...),
    category: str = Form(...),
    date_str: str = Form(...),
    note: str = Form(""),
):
    try:
        amount_val = float(amount)
    except ValueError:
        return RedirectResponse(url="/?err=金额必须是数字", status_code=303)

    if amount_val <= 0:
        return RedirectResponse(url="/?err=金额必须大于0", status_code=303)

    r_date = parse_date(date_str)
    if not r_date:
        return RedirectResponse(url="/?err=日期格式不正确", status_code=303)

    if r_type not in ("expense", "income"):
        return RedirectResponse(url="/?err=类型不正确", status_code=303)

    if r_type == "expense":
        if category not in crud.EXPENSE_CATEGORIES:
            return RedirectResponse(url="/?err=支出分类不正确", status_code=303)
    else:
        if category not in crud.INCOME_CATEGORIES:
            return RedirectResponse(url="/?err=收入分类不正确", status_code=303)

    nt = note.strip()[:100] or None

    db = SessionLocal()
    try:
        crud.add_record(db, r_type, amount_val, category, r_date, nt)
    finally:
        db.close()

    return RedirectResponse(url="/", status_code=303)


@app.post("/delete/{record_id}")
def delete(record_id: int):
    db = SessionLocal()
    try:
        crud.delete_record(db, record_id)
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    year: int = 0,
    month: int = 0,
    month_str: str = "",     # 兼容旧参数：YYYY-MM
    week_start: str = "",    # YYYY-MM-DD (optional, full week Monday)
):
    today = date.today()

    # Determine selected year/month
    y, m = today.year, today.month
    if year and month and 1 <= month <= 12:
        y, m = year, month
    elif month_str:
        ym = parse_month_str(month_str)
        if ym:
            y, m = ym

    m_start, m_end = month_range(y, m)

    # years list for dropdown (more product-like)
    years = list(range(today.year - 5, today.year + 2))  # past 5 years to next year
    months = list(range(1, 13))

    db = SessionLocal()
    try:
        # month totals
        m_exp, m_inc, m_bal = crud.summary_totals_range(db, m_start, m_end)

        # weeks (full week in UI, Scheme B stats only within month)
        weeks_full = month_weeks_full(y, m)
        week_rows = []
        for ws_full, we_full in weeks_full:
            stat_start = ws_full if ws_full >= m_start else m_start
            stat_end = we_full if we_full <= m_end else m_end
            if stat_start > stat_end:
                continue

            w_exp, w_inc, w_bal = crud.summary_totals_range(db, stat_start, stat_end)
            week_rows.append(
                {
                    "week_start": ws_full,
                    "week_end": we_full,
                    "in_month_start": stat_start,
                    "in_month_end": stat_end,
                    "expense": w_exp,
                    "income": w_inc,
                    "balance": w_bal,
                }
            )

        selected_week = None
        by_category = []
        if week_start:
            ws = parse_date(week_start)
            if ws:
                for row in week_rows:
                    if row["week_start"] == ws:
                        selected_week = row
                        by_category = crud.summary_by_category_range(
                            db, row["in_month_start"], row["in_month_end"]
                        )
                        break
    finally:
        db.close()

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "app_name": "小账本",
            "selected_year": y,
            "selected_month": m,
            "years": years,
            "months": months,
            "month_start": m_start,
            "month_end": m_end,
            "month_expense": m_exp,
            "month_income": m_inc,
            "month_balance": m_bal,
            "week_rows": week_rows,
            "selected_week": selected_week,
            "by_category": by_category,
        },
    )

