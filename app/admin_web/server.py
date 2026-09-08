# -*- coding: utf-8 -*-
"""Localhost admin API + SPA. Nginx proxies /api and /app here."""
from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import (
    APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, Response,
    UploadFile)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

import config
from app.admin_web import auth, mail_jobs, queries
from lib.tools.logger import logger

ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = int(os.environ.get("YOURCAST_ADMIN_PORT") or "8765")
DIST_DIR = os.path.join(config.BASE_DIR, "admin", "web", "dist")
COOKIE_KW = {
    "httponly": True,
    "secure": bool(getattr(config, "server", False)),
    "samesite": "lax",
    "path": "/",
    "max_age": auth.SESSION_TTL_SEC,
}

app = FastAPI(title="Yourcast admin", docs_url=None, redoc_url=None)
api = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    mail: str
    password: str


class TariffBody(BaseModel):
    id: int
    level: int
    price: int
    notify_count: int
    compression: int = 0
    channel_control: int = 0


class _NoCacheHTML(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/app"):
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault(
                "Referrer-Policy", "same-origin")
        return response


def _csrf_ok(request: Request) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    host = (request.headers.get("host") or "").split(":")[0].lower()
    origin = request.headers.get("origin")
    if origin:
        return (urlparse(origin).hostname or "").lower() == host
    referer = request.headers.get("referer")
    if referer:
        return (urlparse(referer).hostname or "").lower() == host
    return host in {"testserver", "127.0.0.1", "localhost"}


class _Csrf(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and not _csrf_ok(request):
            return JSONResponse({"detail": "bad origin"}, status_code=403)
        return await call_next(request)


app.add_middleware(_Csrf)
app.add_middleware(_NoCacheHTML)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip") or request.headers.get(
        "x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def current_admin(request: Request) -> dict:
    payload = auth.read_session(request.cookies.get(auth.COOKIE_NAME))
    if not payload:
        raise HTTPException(status_code=401, detail="auth required")
    return payload


@api.get("/health")
def health():
    return {"ok": True}


@api.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = _client_ip(request)
    if not auth.login_allowed(ip):
        raise HTTPException(status_code=429, detail="Слишком много попыток")
    admin = queries.find_admin(body.mail.strip(), body.password)
    if not admin:
        auth.register_login_failure(ip)
        raise HTTPException(status_code=401, detail="Неверная почта или пароль")
    auth.clear_login_failures(ip)
    response.set_cookie(
        auth.COOKIE_NAME, auth.sign_session(admin["id"], admin["mail"]),
        **COOKIE_KW)
    return {"ok": True, "mail": admin["mail"]}


@api.post("/logout")
def logout(response: Response, _admin: dict = Depends(current_admin)):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@api.get("/me")
def me(admin: dict = Depends(current_admin)):
    return {"id": admin["id"], "mail": admin["mail"]}


@api.get("/stats")
def stats(_admin: dict = Depends(current_admin)):
    return queries.stats()


@api.get("/users")
def users(
        page: int = 1,
        tgid: Optional[str] = None,
        _admin: dict = Depends(current_admin)):
    return queries.list_users(page=page, tgid=tgid)


@api.get("/tariffs")
def tariffs(_admin: dict = Depends(current_admin)):
    return {"tariffs": queries.list_tariffs()}


@api.post("/tariffs")
def save_tariff(body: TariffBody, _admin: dict = Depends(current_admin)):
    row = queries.update_tariff(
        body.id, body.level, body.price, body.notify_count,
        body.compression, body.channel_control)
    if row is None:
        raise HTTPException(status_code=404, detail="tariff not found")
    return row


@api.get("/mail")
def mail_list(_admin: dict = Depends(current_admin)):
    return {"jobs": mail_jobs.list_jobs()}


@api.get("/mail/{job_id}")
def mail_one(job_id: int, _admin: dict = Depends(current_admin)):
    job = mail_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@api.post("/mail/{job_id}/cancel")
def mail_cancel(job_id: int, _admin: dict = Depends(current_admin)):
    job = mail_jobs.request_cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@api.post("/mail/{job_id}/resume")
def mail_resume(job_id: int, _admin: dict = Depends(current_admin)):
    job = mail_jobs.resume(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.get("can_resume") and job.get("status") != mail_jobs.STATUS_QUEUED:
        raise HTTPException(status_code=409, detail="cannot resume")
    return job


@api.post("/mail")
async def mail_create(
        request: Request,
        message: str = Form(...),
        parse_mode: str = Form(""),
        attachment_type: str = Form(""),
        to_creator_only: str = Form("true"),
        recipients_identifiers: str = Form(""),
        language: str = Form(""),
        attachments: list[UploadFile] = File(default=[]),
        admin: dict = Depends(current_admin)):
    if not message.strip():
        raise HTTPException(status_code=400, detail="message required")
    only_creator = str(to_creator_only).lower() in ("1", "true", "on", "yes")
    job = mail_jobs.enqueue(
        message=message,
        parse_mode=parse_mode,
        attachment_type=attachment_type,
        to_creator_only=only_creator,
        recipients_text=recipients_identifiers,
        language=language.strip() or None,
        created_by=admin["mail"],
    )
    saved = []
    files = [f for f in attachments if f is not None and f.filename]
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="too many files")
    if files:
        folder = mail_jobs.attachments_dir(job["id"], config.work_dir)
        for upload in files:
            name = _safe_filename(upload.filename or "file")
            path = os.path.join(folder, name)
            data = await upload.read()
            if len(data) > 15 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="file too large")
            with open(path, "wb") as fh:
                fh.write(data)
            saved.append({"path": path, "filename": name})
        job = mail_jobs.set_attachments(job["id"], saved)
    logger.log(
        "admin mail queued", job["id"], "by", admin["mail"],
        "creator_only", only_creator,
        "ip", _client_ip(request))
    return job


def _safe_filename(name: str) -> str:
    base = os.path.basename(name).replace("\x00", "")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base or "file"


@app.exception_handler(Exception)
async def generic_error(_request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    logger.err("admin api:", exc)
    return JSONResponse({"detail": "internal error"}, status_code=500)


app.include_router(api)


@app.get("/app")
@app.get("/app/")
@app.get("/app/{full_path:path}")
def spa(full_path: str = ""):
    if os.path.isdir(DIST_DIR):
        dist = os.path.abspath(DIST_DIR)
        asset = os.path.abspath(os.path.join(dist, full_path))
        if full_path and (
                asset == dist or asset.startswith(dist + os.sep)
        ) and os.path.isfile(asset):
            return FileResponse(asset)
        index = os.path.join(dist, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
    raise HTTPException(status_code=503, detail="admin ui is not built")


def serve():
    import uvicorn
    mail_jobs.ensure_table()
    logger.log("admin api listening", "http://%s:%s" % (ADMIN_HOST, ADMIN_PORT))
    uvicorn.run(
        app, host=ADMIN_HOST, port=ADMIN_PORT, log_level="info",
        access_log=False)


if __name__ == "__main__":
    serve()
