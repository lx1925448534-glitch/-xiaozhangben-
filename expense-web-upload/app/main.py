from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import SessionLocal, engine, Base
from app import models, crud
from app.auth import hash_password, verify_password, get_current_user_id, SESSION_COOKIE

app = FastAPI()

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _parse_date_any(s: str) -> date:
    ss = (s or "").strip().replace("/", "-")
    return datetime.strptime(ss, "%Y-%m-%d").date()


def _require_login(request: Request) -> int:
    uid = get_current_user_id(request)
    if not uid:
        # not logged in
        raise RuntimeError("NOT_LOGGED_IN")
    return uid


@app.get("/health")
def health():
    return JSONResponse({"ok": True})


# ---------- Auth ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
def login_post(
    username: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()
    try:
        u = crud.get_user_by_username(db, username.strip())
        if not u or not verify_password(password, u.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {"request": Request, "error": "用户名或密码错误"},
                status_code=401,
            )
    finally:
        db.close()

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, str(u.id), httponly=True, samesite="lax")
    return resp


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": ""})


@app.post("/register")
def register_post(
    username: str = Form(...),
    password: str = Form(...),
):
    db = SessionLocal()
    try:
        username = username.strip()
        if crud.get_user_by_username(db, username):
            return templates.TemplateResponse(
                "register.html",
                {"request": Request, "error": "用户名已存在"},
                status_code=400,
            )
        u = crud.create_user(db, username=username, password_hash=hash_password(password))
    finally:
        db.close()

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, str(u.id), httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------- App ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()
    try:
        records = crud.list_records(db, user_id=uid, limit=200)

        # 本月统计（用 crud.month_range）
        month = date.today().strftime("%Y-%m")
        start, end = crud.month_range(month)
        summary = crud.range_summary(db, uid, start, min(end, date.today()))
    finally:
        db.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "records": records,
            "total_expense": f"{summary['expense']:.2f}",
            "total_income": f"{summary['income']:.2f}",
            "balance": f"{summary['balance']:.2f}",
        },
    )


@app.post("/add")
def add_post(
    request: Request,
    type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    note: str = Form(""),
):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    t = (type or "").strip()
    if t not in ("expense", "income"):
        t = "expense"

    d = _parse_date_any(date)

    db = SessionLocal()
    try:
        crud.create_record(
            db=db,
            user_id=uid,
            type_=t,
            amount=float(amount),
            category=(category or "").strip(),
            d=d,
            note=(note or "").strip(),
        )
    finally:
        db.close()

    return RedirectResponse(url="/", status_code=303)


@app.post("/delete/{record_id}")
def delete_post(request: Request, record_id: int):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()
    try:
        crud.delete_record(db, user_id=uid, record_id=record_id)
    finally:
        db.close()
    return RedirectResponse(url="/", status_code=303)


# ---------- Stats: month/week + category ----------
@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    mode: str = Query(default="month"),     # "month" or "week"
    month: Optional[str] = Query(default=None),
    week: Optional[str] = Query(default=None),
):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    today = date.today()

    if mode == "week":
        week_value = week or today.isocalendar()
        if isinstance(week_value, tuple):
            # shouldn't happen from querystring; just for safety
            week_value = f"{today.year}-W{today.isocalendar().week:02d}"
        start, end = crud.week_range(week or f"{today.year}-W{today.isocalendar().week:02d}")
        label = f"周：{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
    else:
        m = month or today.strftime("%Y-%m")
        start, end = crud.month_range(m)
        label = f"月：{m}"

    db = SessionLocal()
    try:
        summary = crud.range_summary(db, uid, start, end)
        exp_cat = crud.category_breakdown(db, uid, start, end, "expense")
        inc_cat = crud.category_breakdown(db, uid, start, end, "income")
    finally:
        db.close()

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "mode": mode,
            "label": label,
            "month_value": month or today.strftime("%Y-%m"),
            "week_value": week or f"{today.year}-W{today.isocalendar().week:02d}",
            "summary": summary,
            "expense_categories": exp_cat,
            "income_categories": inc_cat,
        },
    )
