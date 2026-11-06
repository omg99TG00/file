"""Session cookies + login helpers."""
import os
import secrets
from functools import wraps
from typing import Optional

from flask import request, jsonify, g, redirect, url_for

from app.db import get_client, audit
from app.crypto_util import verify_password

SESSION_COOKIE = "owo_sid"


def create_session(user_id: int) -> str:
    sid = secrets.token_urlsafe(32)
    get_client().table("sessions").insert({"id": sid, "user_id": user_id}).execute()
    return sid


def destroy_session(sid: str) -> None:
    if not sid:
        return
    try:
        get_client().table("sessions").delete().eq("id", sid).execute()
    except Exception:
        pass


def load_user_from_session() -> Optional[dict]:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    sb = get_client()
    res = sb.table("sessions").select("user_id").eq("id", sid).limit(1).execute()
    if not res.data:
        return None
    uid = res.data[0]["user_id"]
    u = sb.table("users").select("*").eq("id", uid).limit(1).execute()
    if not u.data:
        return None
    user = u.data[0]
    if user.get("disabled"):
        return None
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = load_user_from_session()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Not logged in."}), 401
            return redirect("/")
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = load_user_from_session()
        if not user or user.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Admin only."}), 403
            return redirect("/")
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def attempt_login(username: str, password: str) -> tuple[bool, str, Optional[dict]]:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False, "Username and password are required.", None
    sb = get_client()
    res = sb.table("users").select("*").eq("username", username).limit(1).execute()
    if not res.data:
        return False, "Invalid username or password.", None
    user = res.data[0]
    if user.get("disabled"):
        return False, "This account has been disabled.", None
    if not verify_password(password, user["password_hash"]):
        return False, "Invalid username or password.", None
    audit(username, "login", "ok")
    return True, "ok", user
