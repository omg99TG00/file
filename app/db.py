"""
Supabase client, schema bootstrap, seed accounts.
"""
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import create_client, Client

# Fixed accounts (password stored hashed at seed time)
SEED_ACCOUNTS = [
    ("pixel_vibe27", "Gt7#k2Qa", "user"),
    ("shadow_fox84", "mR4@v9Lp", "user"),
    ("nova_gamer19", "Xc8#p3Zw", "user"),
    ("cloudy.exe", "bN6@t2Ys", "user"),
    ("its_maverick6", "Hq9#r5Vm", "user"),
    ("echo_rider52", "zK3@w7Fd", "user"),
    ("neonwolf_31", "Pj5#x8Ta", "user"),
    ("chillbyte09", "dL2@q6Rb", "user"),
    ("astro_kid77", "Wm7#n4Cy", "user"),
    ("zenith_playz", "fS9@k3Jv", "user"),
    ("rapid_otter23", "Tz4#b8Hu", "user"),
    ("moonlit_404", "aQ6@x2Ne", "user"),
    ("vortexking8", "Rv3#p7Mk", "user"),
    ("byte_blossom15", "yF8@d5Lc", "user"),
    ("frosty_ninja62", "Jn2#s9Wp", "user"),
    ("lunar_echo5", "cB7@h4Xt", "user"),
    ("driftmode_28", "Zk5#v3Ra", "user"),
    ("cyber_sparrow91", "eM9@w6Uy", "user"),
    ("midnight_ace3", "Lp4#q8Ds", "user"),
    ("orbit_dream46", "xH7@t2Kv", "user"),
    ("deathwalker02", "sheran9_", "admin"),
]

SCHEMA_SQL = [
    """
    create table if not exists users (
      id bigserial primary key,
      username text unique not null,
      password_hash text not null,
      role text not null default 'user',
      disabled boolean not null default false,
      created_at timestamptz not null default now()
    );
    """,
    """
    create table if not exists sessions (
      id text primary key,
      user_id bigint not null references users(id) on delete cascade,
      created_at timestamptz not null default now(),
      expires_at timestamptz
    );
    """,
    """
    create table if not exists deployments (
      id bigserial primary key,
      user_id bigint not null references users(id) on delete cascade,
      name text not null,
      token_enc text not null,
      channel_id text not null,
      huntbot boolean not null default false,
      speed text not null default 'lifetime',
      farm_on boolean not null default false,
      farm_started_at timestamptz,
      farm_ends_at timestamptz,
      cooldown_ends_at timestamptz,
      created_at timestamptz not null default now(),
      unique(user_id)
    );
    """,
    """
    create unique index if not exists deployments_token_enc_uidx on deployments(token_enc);
    """,
    """
    create table if not exists app_meta (
      key text primary key,
      value text not null,
      updated_at timestamptz not null default now()
    );
    """,
    """
    create table if not exists audit_log (
      id bigserial primary key,
      actor text,
      action text not null,
      detail text,
      created_at timestamptz not null default now()
    );
    """,
]

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"].rstrip("/")
        # accept either base or /rest/v1 form
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def _exec_sql(sql: str) -> None:
    """Run raw SQL via rpc if available; otherwise best-effort via postgrest is limited.
    For bootstrap we use the REST sql endpoint when present, else assume tables
    may be created manually once. Primary path: try postgrest-friendly creates
    already listed; if project has no exec_sql, user runs SCHEMA once in SQL editor.
    """
    # supabase-py does not expose arbitrary SQL on all plans.
    # We create via table inserts after ensuring existence by select.
    pass


def ensure_schema() -> None:
    """Idempotent bootstrap: try to read each table; if missing, instruct is logged.
    Tables are created by running SCHEMA_SQL in Supabase SQL Editor once,
    or we attempt insert-based detection. For reliability on free tier we
    document one-time SQL paste; runtime still works if tables exist.
    """
    sb = get_client()
    # Probe users table
    try:
        sb.table("users").select("id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            "Supabase tables missing. Open SQL Editor and paste contents of "
            "schema.sql then re-deploy. Detail: " + str(e)
        )


def seed_users_if_empty(hash_fn) -> None:
    sb = get_client()
    res = sb.table("users").select("id").limit(1).execute()
    if res.data:
        return
    rows = []
    for username, password, role in SEED_ACCOUNTS:
        rows.append(
            {
                "username": username,
                "password_hash": hash_fn(password),
                "role": role,
                "disabled": False,
            }
        )
    sb.table("users").insert(rows).execute()
    audit("system", "seed_users", f"seeded {len(rows)} accounts")


def audit(actor: str, action: str, detail: str = "") -> None:
    try:
        get_client().table("audit_log").insert(
            {"actor": actor, "action": action, "detail": detail}
        ).execute()
    except Exception:
        pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
