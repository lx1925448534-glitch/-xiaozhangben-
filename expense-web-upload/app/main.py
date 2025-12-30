from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.db import SessionLocal, engine
from app import models, crud

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# DB dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 首页：展示最近记录 + 月统计（保持你原来的逻辑）
@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    records = crud.list_recent(db)
    summary = crud.month_summary(db)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "records": records,
            "summary": summary,
        },
    )


# 添加记录（关键修复点）
@app.post("/add")
def add_record(
    r_type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date_str: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    crud.create_record(
        db=db,
        r_type=r_type,
        amount=amount,
        category=category,
        date=date,
        note=note,
    )
    return RedirectResponse("/", status_code=303)


# 统计页（月统计，给后面饼图用）
@app.get("/stats")
def stats(request: Request, db: Session = Depends(get_db)):
    summary = crud.month_summary(db)
    by_category = crud.category_summary(db)
    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "summary": summary,
            "by_category": by_category,
        },
    )



