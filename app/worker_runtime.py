"""
Live selfbot runners. Max GLOBAL_SLOT_CAP concurrent.
Host memory only for live clients; all durable state in Supabase.
"""
import asyncio
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from app.db import get_client, audit, now_utc
from app.crypto_util import decrypt_token

GLOBAL_SLOT_CAP = int(os.environ.get("GLOBAL_SLOT_CAP", "3"))
FARM_DURATION = int(os.environ.get("FARM_DURATION_SECONDS", "10800"))
COOLDOWN = int(os.environ.get("COOLDOWN_SECONDS", "10800"))

# deployment_id -> runtime info
_live: Dict[int, dict] = {}
_lock = threading.Lock()


SPEED_DELAYS = {
    "efficient": (5.0, 15.0, 0.5),
    "fast": (4.5, 10.0, 0.3),
    "durable": (6.5, 21.0, 0.35),
    "lifetime": (7.0, 22.0, 0.4),
}

COMMANDS = [
    "owoh",
    "owo pray",
    "owo h",
    "owo b",
    "owob",
    "owo cf 1",
    "owo s 2",
    "owo pup",
    "owo army",
    "owo roll",
]


def active_count() -> int:
    with _lock:
        return len(_live)


def is_running(deployment_id: int) -> bool:
    with _lock:
        return deployment_id in _live


def list_live() -> list:
    with _lock:
        out = []
        for did, info in _live.items():
            out.append(
                {
                    "deployment_id": did,
                    "username": info.get("username"),
                    "name": info.get("name"),
                    "ends_at": info.get("ends_at"),
                    "speed": info.get("speed"),
                    "huntbot": info.get("huntbot"),
                }
            )
        return out


def _set_farm_off(deployment_id: int, cooldown: bool = True) -> None:
    sb = get_client()
    now = now_utc()
    payload = {
        "farm_on": False,
        "farm_started_at": None,
        "farm_ends_at": None,
    }
    if cooldown:
        payload["cooldown_ends_at"] = (now + timedelta(seconds=COOLDOWN)).isoformat()
    sb.table("deployments").update(payload).eq("id", deployment_id).execute()


def stop_worker(deployment_id: int, reason: str = "stop", skip_cooldown: bool = False) -> None:
    with _lock:
        info = _live.pop(deployment_id, None)
    if info:
        info["stop_flag"] = True
        bot = info.get("bot")
        if bot is not None:
            try:
                asyncio.run_coroutine_threadsafe(bot.close(), info["loop"])
            except Exception:
                pass
        audit("system", "farm_stop", f"deployment={deployment_id} reason={reason}")
    _set_farm_off(deployment_id, cooldown=not skip_cooldown)


def force_stop_all() -> None:
    ids = list(_live.keys())
    for did in ids:
        stop_worker(did, reason="force_all", skip_cooldown=False)


def _run_bot_thread(deployment_id: int, token: str, channel_id: int, speed: str, huntbot: bool, ends_at: datetime, meta: dict):
    import random
    import discord
    from discord.ext import commands

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = commands.Bot(command_prefix=".", self_bot=True)
    bot.remove_command("help")

    with _lock:
        if deployment_id in _live:
            _live[deployment_id]["bot"] = bot
            _live[deployment_id]["loop"] = loop
            _live[deployment_id]["stop_flag"] = False

    async def farm_loop():
        await bot.wait_until_ready()
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                stop_worker(deployment_id, reason="bad_channel")
                return

        delay_min, delay_max, cmd_delay = SPEED_DELAYS.get(speed, SPEED_DELAYS["lifetime"])
        if huntbot:
            try:
                await channel.send("owo hb")
                await asyncio.sleep(3)
            except Exception:
                pass

        while True:
            with _lock:
                info = _live.get(deployment_id)
                if not info or info.get("stop_flag"):
                    break
                if datetime.now(timezone.utc) >= ends_at:
                    break
            cmd = random.choice(COMMANDS)
            try:
                await channel.send(cmd)
            except Exception:
                stop_worker(deployment_id, reason="send_fail")
                return
            await asyncio.sleep(cmd_delay)
            await asyncio.sleep(random.uniform(delay_min, delay_max))

        stop_worker(deployment_id, reason="timer_or_stop")

    @bot.event
    async def on_ready():
        bot.loop.create_task(farm_loop())

    try:
        loop.run_until_complete(bot.start(token))
    except Exception as e:
        audit("system", "farm_error", f"deployment={deployment_id} err={e}")
        stop_worker(deployment_id, reason="login_fail")
    finally:
        try:
            loop.run_until_complete(bot.close())
        except Exception:
            pass
        loop.close()
        with _lock:
            _live.pop(deployment_id, None)


def try_start_farm(deployment: dict, username: str) -> tuple[bool, str]:
    """Returns (ok, message)."""
    sb = get_client()
    # global pause
    try:
        meta = sb.table("app_meta").select("value").eq("key", "global_pause").limit(1).execute()
        if meta.data and meta.data[0]["value"] == "true":
            return False, "Farming is globally paused by admin. Try later."
    except Exception:
        pass

    did = deployment["id"]
    now = now_utc()

    # cooldown
    cd = deployment.get("cooldown_ends_at")
    if cd:
        try:
            cd_dt = datetime.fromisoformat(cd.replace("Z", "+00:00"))
            if now < cd_dt:
                remaining = int((cd_dt - now).total_seconds())
                h, rem = divmod(remaining, 3600)
                m, s = divmod(rem, 60)
                return False, f"Cooldown is on cooldown. Available in {h:02d}:{m:02d}:{s:02d}."
        except Exception:
            pass

    with _lock:
        if len(_live) >= GLOBAL_SLOT_CAP:
            return False, "No empty space left, try after a few hours."
        if did in _live:
            return False, "This deployment is already farming."

    # decrypt + validate by attempting connect is done in thread
    try:
        token = decrypt_token(deployment["token_enc"])
    except Exception:
        return False, "Stored token is invalid. Delete this deployment and create a new one."

    try:
        channel_id = int(deployment["channel_id"])
    except Exception:
        return False, "Stored channel id is invalid. Delete this deployment and create a new one."

    ends_at = now + timedelta(seconds=FARM_DURATION)
    # claim in DB first
    sb.table("deployments").update(
        {
            "farm_on": True,
            "farm_started_at": now.isoformat(),
            "farm_ends_at": ends_at.isoformat(),
        }
    ).eq("id", did).execute()

    with _lock:
        if len(_live) >= GLOBAL_SLOT_CAP:
            _set_farm_off(did, cooldown=False)
            return False, "No empty space left, try after a few hours."
        _live[did] = {
            "username": username,
            "name": deployment.get("name"),
            "ends_at": ends_at.isoformat(),
            "speed": deployment.get("speed", "lifetime"),
            "huntbot": bool(deployment.get("huntbot")),
            "stop_flag": False,
        }

    t = threading.Thread(
        target=_run_bot_thread,
        args=(
            did,
            token,
            channel_id,
            deployment.get("speed") or "lifetime",
            bool(deployment.get("huntbot")),
            ends_at,
            {},
        ),
        daemon=True,
        name=f"farm-{did}",
    )
    t.start()
    audit(username, "farm_on", f"deployment={did} ends={ends_at.isoformat()}")
    return True, "Farm started. Runs for 3 hours."


def stop_farm_by_user(deployment_id: int, username: str) -> tuple[bool, str]:
    if not is_running(deployment_id):
        # still clear DB flag
        _set_farm_off(deployment_id, cooldown=True)
        return True, "Farm was not running on this host; state cleared with cooldown."
    stop_worker(deployment_id, reason="user_toggle_off")
    audit(username, "farm_off", f"deployment={deployment_id}")
    return True, "Farm stopped. Cooldown started."
