"""Validate Discord user token + channel id by live check."""
import asyncio
from typing import Tuple


def validate_token_and_channel(token: str, channel_id: str) -> Tuple[bool, str]:
    token = (token or "").strip().strip('"').strip("'")
    channel_id = (channel_id or "").strip()
    if not token or len(token) < 50:
        return False, "Invalid Discord token format."
    if not channel_id.isdigit():
        return False, "Channel ID must be a numeric snowflake."

    async def _check():
        import discord
        from discord.ext import commands

        bot = commands.Bot(command_prefix=".", self_bot=True)
        bot.remove_command("help")
        error = {"msg": None}

        @bot.event
        async def on_ready():
            try:
                ch = bot.get_channel(int(channel_id))
                if ch is None:
                    ch = await bot.fetch_channel(int(channel_id))
                if ch is None:
                    error["msg"] = "Channel not found for this account."
                else:
                    # need send permission ideally
                    perms = ch.permissions_for(ch.guild.me) if getattr(ch, "guild", None) else None
                    if perms is not None and not perms.send_messages:
                        error["msg"] = "Account cannot send messages in that channel."
            except Exception as e:
                error["msg"] = f"Channel check failed: {e}"
            await bot.close()

        try:
            await bot.start(token)
        except discord.LoginFailure:
            error["msg"] = "Discord rejected this token (login failed)."
        except Exception as e:
            if not error["msg"]:
                error["msg"] = f"Validation error: {e}"
        return error["msg"]

    try:
        msg = asyncio.run(_check())
    except Exception as e:
        return False, f"Validation error: {e}"
    if msg:
        return False, msg
    return True, "ok"
