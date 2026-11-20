from pathlib import Path
from secrets import compare_digest, token_urlsafe
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import FormData
from starlette.responses import RedirectResponse

from .db import database
from .models import User

PACKAGE = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE / "templates")
DB = Annotated[Session, Depends(database)]


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def optional_user(request: Request, db: DB) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id is not None else None


def require_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(303, headers={"Location": "/login"})
    return user


CurrentUser = Annotated[User, Depends(require_user)]


async def verified_form(request: Request) -> FormData:
    async with request.form(max_files=0, max_fields=40, max_part_size=16_384) as form:
        token = form.get("csrf")
        expected = request.session.get("csrf")
        if (
            not isinstance(token, str) or not token.isascii()
            or not expected or not compare_digest(token, expected)
        ):
            raise HTTPException(403, "Срок действия формы истёк. Открой её заново.")
        if any("\0" in value for value in form.values()):
            raise HTTPException(400, "Форма содержит недопустимый символ.")
        return form


Form = Annotated[FormData, Depends(verified_form)]


def render(request: Request, template: str, *, user: User | None = None, status: int = 200, **values):
    if "csrf" not in request.session:
        request.session["csrf"] = token_urlsafe(32)
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"user": user, "csrf": request.session["csrf"], **values},
        status_code=status,
    )


def rubles(value) -> str:
    whole, separator, decimals = f"{value:,.2f}".partition(".")
    suffix = "," + decimals.rstrip("0") if separator and decimals.rstrip("0") else ""
    return whole.replace(",", " ") + suffix + " ₽"


templates.env.filters["rubles"] = rubles


def read_int(values, key, low, high, errors, message):
    raw = values[key]
    if raw:
        if len(raw) <= len(str(high)) and raw.isascii() and raw.isdigit() and low <= int(raw) <= high:
            return int(raw)
        errors[key] = message
    return None
