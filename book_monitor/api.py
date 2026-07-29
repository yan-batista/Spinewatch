from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from book_monitor import db, repository
from book_monitor.config import Settings

settings = Settings.from_env()

app = FastAPI(title="Book Price Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    conn = db.connect(settings.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/books")
def get_books(conn=Depends(get_conn)):
    return [
        {"id": book.id, "title": book.title, "isbn13": book.isbn13, "active": book.active}
        for book in repository.list_books(conn)
    ]


@app.get("/stores")
def get_stores(conn=Depends(get_conn)):
    return [
        {"slug": row["slug"], "name": row["name"], "enabled": bool(row["enabled"])}
        for row in repository.list_stores(conn)
    ]
