"""
Public OwO Farm dashboard + admin.
"""
import os
import sys

# ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    make_response,
    g,
    redirect,
)
from dotenv import load_dotenv

load_dotenv()

from app.db import get_client, ensure_schema, seed_users_if_empty, audit, now_utc
from app.crypto_util import hash_password, encrypt_token, decrypt_token, verify_password
from app.auth import (
    SESSION_COOKIE,
    attempt_login,
    create_session,
    destroy_session,
    load_user_from_session,
    login_required,
    admin_required,
)
from app.names import random_deployment_name
from app.validate import validate_token_and_channel
from app import worker_runtime as wr

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")


def _boot():
    ensure_schema()
    seed_users_if_empty(hash_password)


try:
    _boot()
except Exception as e:
    print("BOOT WARN:", e)


# ---------- pages ----------

@app.get("/")
def index():
    user = load_user_from_session()
    if user:
        if user.get("role") == "admin":
            return redirect("/admin")
        return redirect("/dashboard")
    return render_template("login.html")


@app.get("/dashboard")
@login_required
def dashboard():
    if g.user.get("role") == "admin":
        return redirect("/admin")
    return render_template("dashboard.html", username=g.user["username"])


@app.get("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", username=g.user["username"])


# ---------- auth api ----------

@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    ok, msg, user = attempt_login(data.get("username", ""), data.get("password", ""))
    if not ok:
        return jsonify({"ok": False, "error": msg}), 401
    sid = create_session(user["id"])
    resp = make_response(
        jsonify(
            {
                "ok": True,
                "role": user["role"],
                "redirect": "/admin" if user["role"] == "admin" else "/dashboard",
            }
        )
    )
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 365,
    )
    return resp


@app.post("/api/logout")
def api_logout():
    sid = request.cookies.get(SESSION_COOKIE)
    destroy_session(sid or "")
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(SESSION_COOKIE, "", expires=0)
    return resp


@app.get("/api/me")
@login_required
def api_me():
    return jsonify(
        {
            "ok": True,
            "username": g.user["username"],
            "role": g.user["role"],
            "id": g.user["id"],
        }
    )


# ---------- user deployments ----------

@app.get("/api/deployment")
@login_required
def get_deployment():
    sb = get_client()
    res = (
        sb.table("deployments")
        .select(
            "id,name,channel_id,huntbot,speed,farm_on,farm_started_at,farm_ends_at,cooldown_ends_at,created_at"
        )
        .eq("user_id", g.user["id"])
        .limit(1)
        .execute()
    )
    dep = res.data[0] if res.data else None
    if dep:
        dep["live"] = wr.is_running(dep["id"])
        dep["global_active"] = wr.active_count()
        dep["global_cap"] = wr.GLOBAL_SLOT_CAP
    return jsonify({"ok": True, "deployment": dep})


@app.post("/api/deployment")
@login_required
def create_deployment():
    sb = get_client()
    existing = (
        sb.table("deployments").select("id").eq("user_id", g.user["id"]).limit(1).execute()
    )
    if existing.data:
        return jsonify(
            {
                "ok": False,
                "error": "You already have a deployment. Delete it before creating a new one.",
            }
        ), 400

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    channel_id = (data.get("channel_id") or "").strip()

    ok, msg = validate_token_and_channel(token, channel_id)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400

    token_enc = encrypt_token(token)
    # unique token check (index) — also soft check
    try:
        clash = (
            sb.table("deployments").select("id").eq("token_enc", token_enc).limit(1).execute()
        )
        if clash.data:
            return jsonify(
                {
                    "ok": False,
                    "error": "This Discord token is already linked to another deployment.",
                }
            ), 400
    except Exception:
        pass

    name = random_deployment_name()
    row = {
        "user_id": g.user["id"],
        "name": name,
        "token_enc": token_enc,
        "channel_id": channel_id,
        "huntbot": False,
        "speed": "lifetime",
        "farm_on": False,
    }
    try:
        ins = sb.table("deployments").insert(row).execute()
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err:
            return jsonify(
                {
                    "ok": False,
                    "error": "This Discord token is already linked to another deployment.",
                }
            ), 400
        return jsonify({"ok": False, "error": f"Could not save deployment: {e}"}), 500

    audit(g.user["username"], "deployment_create", name)
    dep = ins.data[0] if ins.data else row
    return jsonify({"ok": True, "deployment": {"id": dep.get("id"), "name": name}})


@app.delete("/api/deployment")
@login_required
def delete_deployment():
    sb = get_client()
    res = (
        sb.table("deployments")
        .select("id,farm_on")
        .eq("user_id", g.user["id"])
        .limit(1)
        .execute()
    )
    if not res.data:
        return jsonify({"ok": False, "error": "No deployment to delete."}), 404
    did = res.data[0]["id"]
    if wr.is_running(did):
        wr.stop_worker(did, reason="deleted", skip_cooldown=True)
    sb.table("deployments").delete().eq("id", did).execute()
    audit(g.user["username"], "deployment_delete", str(did))
    return jsonify({"ok": True})


@app.post("/api/deployment/settings")
@login_required
def update_settings():
    sb = get_client()
    res = (
        sb.table("deployments").select("*").eq("user_id", g.user["id"]).limit(1).execute()
    )
    if not res.data:
        return jsonify({"ok": False, "error": "No deployment found."}), 404
    dep = res.data[0]
    data = request.get_json(silent=True) or {}
    payload = {}
    if "huntbot" in data:
        payload["huntbot"] = bool(data["huntbot"])
    if "speed" in data:
        speed = str(data["speed"]).lower()
        if speed not in ("efficient", "fast", "durable", "lifetime"):
            return jsonify({"ok": False, "error": "Invalid speed mode."}), 400
        payload["speed"] = speed
    if not payload:
        return jsonify({"ok": False, "error": "Nothing to update."}), 400
    sb.table("deployments").update(payload).eq("id", dep["id"]).execute()
    audit(g.user["username"], "settings_update", str(payload))
    return jsonify({"ok": True})


@app.post("/api/deployment/farm")
@login_required
def toggle_farm():
    sb = get_client()
    res = (
        sb.table("deployments").select("*").eq("user_id", g.user["id"]).limit(1).execute()
    )
    if not res.data:
        return jsonify({"ok": False, "error": "No deployment found."}), 404
    dep = res.data[0]
    data = request.get_json(silent=True) or {}
    want_on = bool(data.get("on"))

    if want_on:
        ok, msg = wr.try_start_farm(dep, g.user["username"])
        return jsonify({"ok": ok, "error": None if ok else msg, "message": msg if ok else None}), (
            200 if ok else 400
        )
    else:
        ok, msg = wr.stop_farm_by_user(dep["id"], g.user["username"])
        return jsonify({"ok": ok, "message": msg})


# ---------- admin api ----------

@app.get("/api/admin/slots")
@admin_required
def admin_slots():
    live = wr.list_live()
    sb = get_client()
    # enrich from DB
    pause = False
    try:
        m = sb.table("app_meta").select("value").eq("key", "global_pause").limit(1).execute()
        if m.data:
            pause = m.data[0]["value"] == "true"
    except Exception:
        pass
    return jsonify(
        {
            "ok": True,
            "active": live,
            "count": len(live),
            "cap": wr.GLOBAL_SLOT_CAP,
            "global_pause": pause,
        }
    )


@app.post("/api/admin/force-stop")
@admin_required
def admin_force_stop():
    data = request.get_json(silent=True) or {}
    did = data.get("deployment_id")
    skip_cd = bool(data.get("skip_cooldown"))
    if not did:
        return jsonify({"ok": False, "error": "deployment_id required"}), 400
    wr.stop_worker(int(did), reason="admin_force", skip_cooldown=skip_cd)
    audit(g.user["username"], "admin_force_stop", str(did))
    return jsonify({"ok": True})


@app.post("/api/admin/global-pause")
@admin_required
def admin_global_pause():
    data = request.get_json(silent=True) or {}
    pause = bool(data.get("pause"))
    sb = get_client()
    sb.table("app_meta").upsert(
        {"key": "global_pause", "value": "true" if pause else "false", "updated_at": now_utc().isoformat()}
    ).execute()
    if pause and data.get("stop_all"):
        wr.force_stop_all()
    audit(g.user["username"], "global_pause", str(pause))
    return jsonify({"ok": True, "pause": pause})


@app.get("/api/admin/users")
@admin_required
def admin_users():
    sb = get_client()
    users = sb.table("users").select("id,username,role,disabled,created_at").order("id").execute()
    deps = sb.table("deployments").select(
        "id,user_id,name,farm_on,farm_ends_at,cooldown_ends_at,speed,huntbot,channel_id"
    ).execute()
    by_user = {d["user_id"]: d for d in (deps.data or [])}
    out = []
    for u in users.data or []:
        d = by_user.get(u["id"])
        out.append({**u, "deployment": d})
    return jsonify({"ok": True, "users": out})


@app.post("/api/admin/user-disable")
@admin_required
def admin_user_disable():
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    disabled = bool(data.get("disabled"))
    if not uid:
        return jsonify({"ok": False, "error": "user_id required"}), 400
    get_client().table("users").update({"disabled": disabled}).eq("id", uid).execute()
    audit(g.user["username"], "user_disable" if disabled else "user_enable", str(uid))
    return jsonify({"ok": True})


@app.post("/api/admin/force-delete-deployment")
@admin_required
def admin_force_delete():
    data = request.get_json(silent=True) or {}
    did = data.get("deployment_id")
    if not did:
        return jsonify({"ok": False, "error": "deployment_id required"}), 400
    did = int(did)
    if wr.is_running(did):
        wr.stop_worker(did, reason="admin_delete", skip_cooldown=True)
    get_client().table("deployments").delete().eq("id", did).execute()
    audit(g.user["username"], "admin_delete_deployment", str(did))
    return jsonify({"ok": True})


@app.post("/api/admin/clear-cooldown")
@admin_required
def admin_clear_cooldown():
    data = request.get_json(silent=True) or {}
    did = data.get("deployment_id")
    if not did:
        return jsonify({"ok": False, "error": "deployment_id required"}), 400
    get_client().table("deployments").update({"cooldown_ends_at": None}).eq("id", did).execute()
    audit(g.user["username"], "clear_cooldown", str(did))
    return jsonify({"ok": True})


@app.post("/api/admin/change-password")
@admin_required
def admin_change_password():
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    new_pw = data.get("password") or ""
    if not uid or len(new_pw) < 4:
        return jsonify({"ok": False, "error": "user_id and password (min 4) required"}), 400
    get_client().table("users").update({"password_hash": hash_password(new_pw)}).eq(
        "id", uid
    ).execute()
    audit(g.user["username"], "change_password", str(uid))
    return jsonify({"ok": True})


@app.get("/api/admin/audit")
@admin_required
def admin_audit():
    res = (
        get_client()
        .table("audit_log")
        .select("*")
        .order("id", desc=True)
        .limit(100)
        .execute()
    )
    return jsonify({"ok": True, "logs": res.data or []})


@app.get("/api/admin/health")
@admin_required
def admin_health():
    return jsonify(
        {
            "ok": True,
            "active_workers": wr.active_count(),
            "cap": wr.GLOBAL_SLOT_CAP,
            "live": wr.list_live(),
        }
    )


def create_app():
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    from waitress import serve

    print(f"Serving on 0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port)
