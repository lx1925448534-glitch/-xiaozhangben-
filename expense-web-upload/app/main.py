from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import SessionLocal, engine, Base
from app import crud
from app.auth import hash_password, verify_password, get_current_user_id, SESSION_COOKIE

app = FastAPI()

# 建表（清库后会重建）
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _parse_date_any(s: str) -> date:
    ss = (s or "").strip().replace("/", "-")
    return datetime.strptime(ss, "%Y-%m-%d").date()


def _require_login(request: Request) -> Optional[int]:
    return get_current_user_id(request)


@app.get("/health")
def health():
    return JSONResponse({"ok": True})


# ---------------- Auth ----------------
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": ""})


@app.post("/register")
def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    username = (username or "").strip()
    password = password or ""

    if not username:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "用户名不能为空"}, status_code=400
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "密码至少 6 位"}, status_code=400
        )

    db = SessionLocal()
    try:
        if crud.get_user_by_username(db, username):
            return templates.TemplateResponse(
                "register.html", {"request": request, "error": "用户名已存在"}, status_code=400
            )
        u = crud.create_user(db, username=username, password_hash=hash_password(password))
    finally:
        db.close()

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(SESSION_COOKIE, str(u.id), httponly=True, samesite="lax")
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    username = (username or "").strip()
    password = password or ""

    db = SessionLocal()
    try:
        u = crud.get_user_by_username(db, username)
        if (not u) or (not verify_password(password, u.password_hash)):
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "用户名或密码错误"}, status_code=401
            )
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


# ---------------- Admin: 查账号&哈希 + 重置密码 ----------------
# ⚠️ 注意：这里显示的是 password_hash，不是明文密码（明文无法取回）
@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, key: str = Query(default="")):
    """
    简单的后台查看页：需要 ?key=你自定义的密钥
    你需要在 Render 环境变量里设置 ADMIN_KEY
    """
    import os
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or key != admin_key:
        return HTMLResponse("Forbidden", status_code=403)

    db = SessionLocal()
    try:
        users = crud.list_users(db)
    finally:
        db.close()

    # 简单输出（不新建模板也能用）
    html = ["<h2>用户列表</h2>", "<p>注意：这里只能看到密码哈希，不能看到明文密码。</p>"]
    html.append("<table border='1' cellpadding='6' cellspacing='0'>")
    html.append("<tr><th>ID</th><th>用户名</th><th>手机号</th><th>创建时间</th><th>password_hash</th></tr>")
    for u in users:
        html.append(
            f"<tr><td>{u.id}</td><td>{u.username}</td><td>{u.phone or ''}</td>"
            f"<td>{u.created_at}</td><td style='max-width:640px;word-break:break-all'>{u.password_hash}</td></tr>"
        )
    html.append("</table>")
    html.append("<p>重置密码接口：POST /admin/reset_password?key=ADMIN_KEY （表单：username,new_password）</p>")
    return HTMLResponse("".join(html))


@app.post("/admin/reset_password")
def admin_reset_password(
    request: Request,
    key: str = Query(default=""),
    username: str = Form(...),
    new_password: str = Form(...),
):
    import os
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or key != admin_key:
        return HTMLResponse("Forbidden", status_code=403)

    username = (username or "").strip()
    if len(new_password) < 6:
        return JSONResponse({"ok": False, "error": "新密码至少6位"}, status_code=400)

    db = SessionLocal()
    try:
        u = crud.get_user_by_username(db, username)
        if not u:
            return JSONResponse({"ok": False, "error": "用户不存在"}, status_code=404)
        crud.update_user_password(db, user_id=u.id, password_hash=hash_password(new_password))
    finally:
        db.close()

    return JSONResponse({"ok": True})


# ---------------- App pages ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    uid = _require_login(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()
    try:
        records = crud.list_records(db, user_id=uid, limit=200)

        # 本月统计
        m = date.today().strftime("%Y-%m")
        start, end = crud.month_range(m)
        summary = crud.range_summary(db, uid, start, end)
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


@app.get("/add")
def add_get_redirect():
    return RedirectResponse(url="/", status_code=302)


@app.post("/add")
def add_post(
    request: Request,
    type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    note: str = Form(""),
):
    uid = _require_login(request)
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
    uid = _require_login(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()
    try:
        crud.delete_record(db, user_id=uid, record_id=record_id)
    finally:
        db.close()

    return RedirectResponse(url="/", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    mode: str = Query(default="month"),
    month: Optional[str] = Query(default=None),
    week: Optional[str] = Query(default=None),
):
    uid = _require_login(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=303)

    today = date.today()

    if mode == "week":
        wk = week or f"{today.year}-W{today.isocalendar().week:02d}"
        start, end = crud.week_range(wk)
        label = f"周：{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
        week_value = wk
        month_value = month or today.strftime("%Y-%m")
    else:
        m = month or today.strftime("%Y-%m")
        start, end = crud.month_range(m)
        label = f"月：{m}"
        month_value = m
        week_value = week or f"{today.year}-W{today.isocalendar().week:02d}"

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
            "month_value": month_value,
            "week_value": week_value,
            "summary": summary,
            "expense_categories": exp_cat,
            "income_categories": inc_cat,
        },
    )
