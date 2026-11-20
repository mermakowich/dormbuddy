import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from .config import get_settings
from .llm import ProviderUnavailable, request_answer
from .models import BuddyConversation, BuddyMessage
from .profiles import MOVE_STAGES
from .web import DB, CurrentUser, Form, redirect, render

router = APIRouter()
PROMPTS = (
    "Что купить для первых дней в общежитии?",
    "Составь чек-лист переезда в Москву.",
    "Помоги распланировать месячный бюджет.",
    "Как организовать быт с новым соседом?",
)


def expiration():
    return datetime.now(UTC) - timedelta(seconds=get_settings().buddy_timeout + 15)


def buddy_page(request, db, user, *, question="", request_id=None, error=None):
    messages = db.scalars(
        select(BuddyMessage).join(BuddyConversation)
        .where(BuddyConversation.user_id == user.id).order_by(BuddyMessage.id)
    ).all()
    settings = get_settings()
    return render(
        request, "buddy.html", user=user, messages=messages, prompts=PROMPTS,
        configured=bool(settings.buddy_api_key.get_secret_value()), cutoff=expiration(),
        question=question, request_id=request_id or str(uuid4()), error=error,
        busy=request.query_params.get("busy") == "1", status=422 if error else 200,
    )


@router.get("/buddy")
def conversation(request: Request, db: DB, user: CurrentUser):
    return buddy_page(request, db, user)


def context_for(profile):
    context = {
        "вуз": profile.university.name if profile.university else None,
        "общежитие": profile.dormitory.name if profile.dormitory else None,
        "район": profile.district,
        "месячная доля аренды, ₽": [profile.budget_min, profile.budget_max] if profile.budget_min else None,
        "интересы": profile.interests,
        "этап переезда": MOVE_STAGES.get(profile.move_stage),
    }
    return {key: value for key, value in context.items() if value is not None}


def lock_conversation(db, user_id):
    db.execute(insert(BuddyConversation).values(user_id=user_id).on_conflict_do_nothing(
        index_elements=[BuddyConversation.user_id]
    ))
    return db.scalar(select(BuddyConversation.id).where(BuddyConversation.user_id == user_id).with_for_update())


def get_history(db, conversation_id, before):
    previous = db.scalars(
        select(BuddyMessage).where(
            BuddyMessage.conversation_id == conversation_id, BuddyMessage.id < before,
            BuddyMessage.status == "answered",
        ).order_by(BuddyMessage.id.desc()).limit(10)
    ).all()
    history = []
    for turn in reversed(previous):
        history.extend([{"role": "user", "content": turn.question}, {"role": "assistant", "content": turn.answer}])
    return history


@router.post("/buddy")
def ask(request: Request, db: DB, user: CurrentUser, form: Form):
    question = form.get("question", "").strip()
    try:
        request_id = str(UUID(form.get("request_id", "")))
    except ValueError:
        raise HTTPException(400, "Открой Buddy заново и повтори запрос.") from None
    retry = form.get("retry") == "1"
    if not retry and not 1 <= len(question) <= 1200:
        return buddy_page(
            request, db, user, question=question, request_id=request_id,
            error="Введи вопрос длиной от 1 до 1200 символов.",
        )

    conversation_id = lock_conversation(db, user.id)
    message = db.scalar(select(BuddyMessage).where(
        BuddyMessage.conversation_id == conversation_id, BuddyMessage.request_id == request_id,
    ))
    if retry and message is None:
        raise HTTPException(404)
    if message and (message.status == "answered" or not retry):
        return redirect(f"/buddy#turn-{message.id}")

    cutoff = expiration()
    pending = db.scalar(select(BuddyMessage.id).where(
        BuddyMessage.conversation_id == conversation_id, BuddyMessage.status == "pending",
        BuddyMessage.started_at >= cutoff,
    ).limit(1))
    if pending is not None:
        if retry:
            return redirect(f"/buddy?busy=1#turn-{pending}")
        return buddy_page(
            request, db, user, question=question, request_id=request_id,
            error="Buddy ещё отвечает на предыдущий вопрос. Попробуй отправить этот чуть позже.",
        )
    db.execute(update(BuddyMessage).where(
        BuddyMessage.conversation_id == conversation_id, BuddyMessage.status == "pending",
        BuddyMessage.started_at < cutoff,
    ).values(status="failed"))
    if message is None:
        message = BuddyMessage(
            conversation_id=conversation_id, request_id=request_id, question=question,
            status="pending", attempt=1, started_at=datetime.now(UTC),
        )
        db.add(message)
    else:
        message.status = "pending"
        message.attempt += 1
        message.started_at = datetime.now(UTC)
    db.flush()
    message_id, attempt, content = message.id, message.attempt, message.question
    context = context_for(user.profile)
    history = get_history(db, conversation_id, message_id)
    db.commit()

    try:
        answer = asyncio.run(request_answer(get_settings(), context, history, content))
    except ProviderUnavailable:
        answer = None

    db.execute(update(BuddyMessage).where(
        BuddyMessage.id == message_id, BuddyMessage.conversation_id == conversation_id,
        BuddyMessage.attempt == attempt, BuddyMessage.status == "pending",
    ).values(answer=answer, status="answered" if answer is not None else "failed"))
    db.commit()
    return redirect(f"/buddy#turn-{message_id}")
