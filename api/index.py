import sys
import traceback
from pathlib import Path
from flask import Flask, jsonify

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "pipeline"))

try:
    from pipeline.web_app import app
except Exception as e:
    err_msg = traceback.format_exc()
    app = Flask(__name__)
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return f"<h3>Vercel Startup Error:</h3><pre>{err_msg}</pre>", 500

