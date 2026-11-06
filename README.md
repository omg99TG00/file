# OwO Farm — Public Dashboard

Shared login farm panel for OwO. Max **3** concurrent farms. Supabase for accounts, deployments, timers. Host only runs live selfbots.

## 1. Supabase (one-time)

1. Create free project at supabase.com.
2. **SQL Editor → New query** → paste entire `schema.sql` → Run.
3. Project Settings → API Keys:
   - **Project URL** (base): `https://xxxx.supabase.co`  
     (or with `/rest/v1/` — both work)
   - **Secret key** (`sb_secret_…` under Secret keys) = service role
4. Keep URL + secret for env vars.

## 2. Generate secrets

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use first as `TOKEN_ENC_KEY`, second as `SECRET_KEY`.

## 3. Environment variables

```
SUPABASE_URL=https://ozkpohdgmcgztvzgugjr.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
TOKEN_ENC_KEY=...fernet key...
SECRET_KEY=...random...
PORT=8080
GLOBAL_SLOT_CAP=3
FARM_DURATION_SECONDS=10800
COOLDOWN_SECONDS=10800
```

## 4. Local test

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# put env in .env or export
python main.py
```

Open http://127.0.0.1:8080

On first successful DB connection, the 21 accounts are seeded automatically (if `users` is empty).

## 5. Deploy (bot-hosting.net)

1. Create Python project / node.
2. Upload repo (or git pull).
3. Set env vars above.
4. Start command: `python main.py` (or `waitress` via main).
5. Open the public URL from the panel.

## 6. Deploy (Railway)

1. New project from GitHub.
2. Add same env vars.
3. Start: `python main.py`
4. Public URL: `*.up.railway.app`

## 7. Accounts

20 user logins (see your list) + admin:

- **Admin:** `deathwalker02` / `sheran9_` → `/admin`

## 8. Behaviour summary

| Action | Rule |
|--------|------|
| Deployments per user | 1 |
| Token | Unique globally; live-validated on create |
| Farm ON | Claims 1 of 3 global slots; runs 3h; then OFF + 3h cooldown |
| Host restart / new project | Clean slate — no auto-resume; first 3 to toggle win |
| HuntBot / Speed | Persist in Supabase; editable anytime |

## 9. Project flip (bot-hosting)

When RAM is tight: new project + **same** Supabase env keys → users stay logged in, deployments intact, live farms drop until they toggle ON again on the new host.

## Security notes

- Never commit real `SUPABASE_SERVICE_ROLE_KEY` or `TOKEN_ENC_KEY`.
- Tokens stored encrypted (Fernet).
- Session cookie: HttpOnly, Secure, SameSite=Lax.
