from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from . import auth, buddy, housing, neighbors, profiles, swipes
from .config import get_settings
from .web import PACKAGE, redirect, render

settings = get_settings()
app = FastAPI(title="DormBuddy", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=settings.session_secret.get_secret_value(),
    session_cookie="dormbuddy_session", max_age=60 * 60 * 24, https_only=settings.cookie_secure,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
for module in (auth, profiles, neighbors, swipes, housing, buddy):
    app.include_router(module.router)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    size = request.headers.get("content-length", "")
    if request.method == "POST" and size.isdecimal() and int(size) > 32_768:
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("Форма слишком большая.", status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException):
    if error.status_code == 303:
        return redirect(error.headers["Location"])
    messages = {
        404: "Страница не найдена.",
        405: "Это действие недоступно.",
    }
    message = messages.get(error.status_code, error.detail)
    return render(
        request, "error.html", status=error.status_code, message=message,
        signed_in=bool(request.session.get("user_id")),
    )
