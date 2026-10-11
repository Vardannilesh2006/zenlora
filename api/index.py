import sys
import traceback
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "pipeline"))

_IMPORT_ERROR = None
try:
    from pipeline.web_app import app as flask_app
except Exception:
    _IMPORT_ERROR = traceback.format_exc()
    from flask import Flask
    flask_app = Flask(__name__)


class DiagnosticMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if _IMPORT_ERROR:
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            return [f"<h2>Zenlora Import Error:</h2><pre>{_IMPORT_ERROR}</pre>".encode("utf-8")]
        try:
            return self.wsgi_app(environ, start_response)
        except Exception:
            err = traceback.format_exc()
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            return [f"<h2>Zenlora Serverless Error:</h2><pre>{err}</pre>".encode("utf-8")]


app = flask_app
app.wsgi_app = DiagnosticMiddleware(app.wsgi_app)
application = app
