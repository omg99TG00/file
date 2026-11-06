"""
Entry point for Railway / bot-hosting.
Must run from project root where the `app/` folder lives.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv()

from app.main import app

if __name__ == "__main__":
    # bot-hosting uses SERVER_PORT; Railway/others use PORT
    port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or "8080")
    from waitress import serve

    print(f"OwO Farm listening on 0.0.0.0:{port}")
    print(f"Root: {ROOT}")
    serve(app, host="0.0.0.0", port=port)
