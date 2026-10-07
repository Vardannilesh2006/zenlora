import sys
import traceback
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "pipeline"))

from pipeline.web_app import app

class DiagnosticMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        try:
            return self.wsgi_app(environ, start_response)
        except Exception as e:
            err = traceback.format_exc()
            start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            return [f"<h2>Zenlora Serverless Error:</h2><pre>{err}</pre>".encode("utf-8")]

app.wsgi_app = DiagnosticMiddleware(app.wsgi_app)
application = app



