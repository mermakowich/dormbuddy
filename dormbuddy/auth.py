from secrets import token_urlsafe

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .models import Preferences, Profile, User
from .web import DB, CurrentUser, Form, optional_user, redirect, render

router = APIRouter()
passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(token_urlsafe(32))


def normalize_email(value: str) -> str:
    if len(value) > 254:
        raise EmailNotValidError("Email is too long")
    return validate_email(value.strip(), check_deliverability=False).normalized.casefold()


def authenticate(request: Request, user_id: int):
    request.session.clear()
    request.session.update(user_id=user_id, csrf=token_urlsafe(32))


@router.get("/")
def home(user: User | None = Depends(optional_user)):
    return redirect("/neighbors" if user else "/login")


@router.get("/login")
@router.get("/register")
def auth_page(request: Request, user: User | None = Depends(optional_user)):
    if user:
        return redirect("/neighbors")
    return render(request, "auth.html", register=request.url.path == "/register")


@router.post("/register")
def register(request: Request, db: DB, form: Form):
    raw_email, password = form.get("email", ""), form.get("password", "")
    errors = {}
    try:
        email = normalize_email(raw_email)
    except EmailNotValidError:
        errors["email"] = "Введи действительный email."
    if not 10 <= len(password) <= 128:
        errors["password"] = "Пароль должен содержать от 10 до 128 символов."
    if not errors:
        user_id = db.scalar(
            insert(User).values(email=email, password_hash=passwords.hash(password))
            .on_conflict_do_nothing(index_elements=[User.email]).returning(User.id)
        )
        if user_id is not None:
            db.add(Profile(user_id=user_id, preferences=Preferences()))
            db.commit()
            authenticate(request, user_id)
            return redirect("/profile")
        errors["email"] = "Этот email уже зарегистрирован. Войди в аккаунт."
    return render(request, "auth.html", status=422, register=True, email=raw_email, errors=errors)


@router.post("/login")
def login(request: Request, db: DB, form: Form):
    raw_email, password = form.get("email", ""), form.get("password", "")
    try:
        email = normalize_email(raw_email)
    except EmailNotValidError:
        email = None
    user = db.scalar(select(User).where(User.email == email)) if email else None
    try:
        valid_password = len(password) <= 128 and passwords.verify(
            user.password_hash if user else DUMMY_HASH, password
        )
    except VerificationError:
        valid_password = False
    if not user or not valid_password:
        return render(
            request, "auth.html", status=401, email=raw_email,
            errors={"credentials": "Email или пароль не подошёл. Проверь данные и попробуй ещё раз."},
        )
    destination = "/neighbors" if user.profile.display_name else "/profile"
    if passwords.check_needs_rehash(user.password_hash):
        user.password_hash = passwords.hash(password)
        db.commit()
    authenticate(request, user.id)
    return redirect(destination)


@router.post("/logout")
def logout(request: Request, user: CurrentUser, form: Form):
    request.session.clear()
    return redirect("/login")
