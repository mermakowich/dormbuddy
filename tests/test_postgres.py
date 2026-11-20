import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dormbuddy import buddy, llm
from dormbuddy.config import get_settings
from dormbuddy.main import app
from dormbuddy.models import BuddyMessage, Dormitory, Favorite, HousingListing, Match, Profile, Swipe, User
from dormbuddy.seed import seed

PASSWORD = "DormBuddy-test-password"
CSRF = re.compile(r'name="csrf" value="([^"]+)"')
REQUEST_ID = re.compile(r'name="request_id" value="([^"]+)"')
PROFILE = {
    "display_name": "Демо Студент", "mode": "rent", "district": "Хамовники", "budget_min": "26000",
    "budget_max": "30000", "smokes": "no", "allows_smoking": "no", "has_pet": "no", "allows_pets": "yes",
    "sleep": "early", "cleaning": "4",
}


def page_token(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return CSRF.search(response.text)[1]


def post(client, path, csrf, **data):
    return client.post(path, data={"csrf": csrf, **data}, follow_redirects=False)


def login(name):
    client = TestClient(app)
    response = post(client, "/login", page_token(client, "/login"), email=f"{name}@example.com", password=PASSWORD)
    assert response.status_code == 303
    return client


def account_id(engine, name):
    with Session(engine) as db:
        return db.scalar(select(User.id).where(User.email == f"{name}@example.com"))


def demo(engine):
    with Session(engine) as db:
        seed(db, PASSWORD)


def test_auth_owner_csrf_and_recommendations(postgres):
    demo(postgres)
    client = TestClient(app)
    assert client.get("/profile", follow_redirects=False).headers["location"] == "/login"
    csrf = page_token(client, "/register")
    assert post(client, "/register", "invalid", email="sam@example.com", password=PASSWORD).status_code == 403
    bad = post(client, "/register", csrf, email="bad-email", password="short")
    assert bad.status_code == 422 and "действительный email" in bad.text and "10 до 128" in bad.text
    registered = post(client, "/register", csrf, email="SAM@example.com", password=PASSWORD)
    assert registered.headers["location"] == "/profile"
    assert all(flag in registered.headers["set-cookie"].lower() for flag in ("httponly", "samesite=lax"))
    assert "Заполни условия" in client.get("/neighbors").text
    assert "Учебное объявление" in client.get("/housing").text
    csrf = page_token(client, "/profile")
    broken = post(client, "/profile", csrf, **(PROFILE | {"budget_min": "31000"}))
    assert broken.status_code == 422 and "верхняя граница" in broken.text.lower()
    assert post(client, "/profile", csrf, **PROFILE, user_id=account_id(postgres, "alisa")).status_code == 303
    with Session(postgres) as db:
        mine = db.get(Profile, account_id(postgres, "sam"))
        assert mine.display_name == PROFILE["display_name"] and mine.smokes is False and mine.preferences.guests is None
        assert db.get(Profile, account_id(postgres, "alisa")).display_name == "Алиса"
        assert db.get(User, mine.user_id).password_hash.startswith("$argon2id$")
    result = client.get("/neighbors").text
    assert "Алиса" in result and "Сопоставлено 2 из 6" in result and "100<span>%" in result
    assert post(client, "/profile", csrf, **(PROFILE | {"cleaning": "2"})).status_code == 303
    assert "Борис" in client.get("/neighbors").text
    assert post(client, "/logout", csrf).status_code == 303
    assert client.get("/profile", follow_redirects=False).status_code == 303
    csrf = page_token(client, "/login")
    assert post(client, "/login", csrf, email="SAM@EXAMPLE.COM", password="wrong").status_code == 401
    assert post(client, "/login", csrf, email="SAM@EXAMPLE.COM", password=PASSWORD).status_code == 303
    other = TestClient(app)
    assert post(other, "/register", page_token(other, "/register"), email="sam@example.com", password=PASSWORD).status_code == 422


def test_dormitory_directory_and_feed(postgres):
    demo(postgres)
    client = login("nadya")
    before = client.get("/neighbors").text
    assert "Олег" in before and "Соня" not in before and "Расселением занимается вуз" in before
    with Session(postgres) as db:
        dorm_2 = db.scalar(select(Dormitory).where(Dormitory.name == "Общежитие № 2"))
        misis, dorm_id = dorm_2.university_id, dorm_2.id
        wrong_dorm = db.scalar(select(Dormitory.id).where(Dormitory.university_id != misis))
    data = PROFILE | {"mode": "dorm", "university_id": str(misis), "dorm_scope": "dormitory"}
    csrf = page_token(client, "/dormitory")
    invalid = post(client, "/profile", csrf, **(data | {"dormitory_id": str(wrong_dorm)}))
    assert invalid.status_code == 422 and "Выбери общежитие этого вуза" in invalid.text
    assert post(client, "/profile", csrf, **(data | {"dormitory_id": str(dorm_id)})).status_code == 303
    after = client.get("/neighbors").text
    assert "Соня" in after and "Олег" not in after and "Общежитие № 2" in after


def test_like_skip_replay_and_shared_housing(postgres):
    demo(postgres)
    alice, boris, vera = login("alisa"), login("boris"), login("vera")
    alice_id, boris_id, mila_id = [account_id(postgres, name) for name in ("alisa", "boris", "mila")]
    alice_token = page_token(alice, "/neighbors")
    boris_token = page_token(boris, "/neighbors")

    assert post(alice, f"/neighbors/{alice_id}/swipe", alice_token, action="like").status_code == 400
    assert post(alice, f"/neighbors/{account_id(postgres, 'vera')}/swipe", alice_token, action="like").status_code == 404
    for _ in range(2):
        assert post(alice, f"/neighbors/{boris_id}/swipe", alice_token, action="like").headers["location"] == "/neighbors"
    assert "Пока нет взаимных симпатий" in alice.get("/matches").text
    assert "Мила" in alice.get("/neighbors").text
    assert "Недостаточно данных" in alice.get("/neighbors").text
    for _ in range(2):
        assert post(alice, f"/neighbors/{mila_id}/swipe", alice_token, action="skip").status_code == 303
    assert "Подходящих анкет пока нет" in alice.get("/neighbors").text
    assert post(boris, f"/neighbors/{alice_id}/swipe", boris_token, action="like").headers["location"] == "/neighbors?matched=1"
    for _ in range(2):
        assert post(boris, f"/neighbors/{alice_id}/swipe", boris_token, action="like").status_code == 303

    with Session(postgres) as db:
        match, = db.scalars(select(Match)).all()
        assert (match.first_id, match.second_id) == tuple(sorted((alice_id, boris_id)))
        assert db.scalar(select(func.count()).select_from(Swipe)) == 3
        path = f"/matches/{match.id}/housing"
    assert path in alice.get("/matches").text
    assert path in boris.get("/matches").text
    assert vera.get(path).status_code == 404
    for client in (alice, boris):
        result = client.get(path).text
        assert "Двухкомнатная у Сокола" in result
        assert "Комната на Академической" not in result and "Квартира в Измайлове" not in result


def test_concurrent_reciprocal_likes_postgres(postgres):
    demo(postgres)
    past_lock = Barrier(2)
    alice_id, boris_id = account_id(postgres, "alisa"), account_id(postgres, "boris")
    alice, boris = login("alisa"), login("boris")

    def swipe(client, target):
        token = page_token(client, "/neighbors")
        past_lock.wait(timeout=10)
        return post(client, f"/neighbors/{target}/swipe", token, action="like").headers["location"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        done = [pool.submit(swipe, alice, boris_id), pool.submit(swipe, boris, alice_id)]
        assert {future.result() for future in done} == {"/neighbors", "/neighbors?matched=1"}
    with Session(postgres) as db:
        assert db.scalar(select(func.count()).select_from(Match)) == 1
        assert db.scalar(select(func.count()).select_from(Swipe)) == 2


def test_housing_combined_filters_and_persistent_favorites(postgres):
    demo(postgres)
    demo(postgres)
    alice, vera = login("alisa"), login("vera")
    path = "/housing?minimum=30000&maximum=30000&location=сокол&kind=apartment&pets=yes&smoking=no"
    matched = vera.get(path)
    assert matched.status_code == 200
    assert matched.text.count("Учебное объявление") == 1
    assert "Двухкомнатная у Сокола" in matched.text and "Сбросить фильтры" in matched.text
    assert "Варианты не найдены" in vera.get(path.replace("30000", "29999")).text
    assert vera.get("/housing?minimum=40000&maximum=39000").status_code == 422
    with Session(postgres) as db:
        assert db.scalar(select(func.count()).select_from(HousingListing)) == 5
        listing = db.scalar(select(HousingListing.id).where(HousingListing.slug == "sokol-apartment"))
        action = f"/housing/{listing}/favorite"
    csrf = page_token(vera, "/housing")
    for _ in range(2):
        assert post(vera, action, csrf, action="add", source="favorites").status_code == 303
    assert "Двухкомнатная у Сокола" in login("vera").get("/housing/favorites").text
    for _ in range(2):
        assert post(vera, action, csrf, action="remove", source="favorites").status_code == 303
    assert "В избранном пока пусто" in vera.get("/housing/favorites").text
    assert "Двухкомнатная у Сокола" in alice.get("/housing/favorites").text
    with Session(postgres) as db:
        assert db.get(Favorite, (account_id(postgres, "vera"), listing)) is None


def test_buddy_fake_http_context_history_retry_and_ownership(postgres, monkeypatch):
    demo(postgres)
    settings = get_settings().model_copy(update={
        "buddy_api_key": SecretStr("test-token"), "buddy_base_url": "https://llm.example/v1",
        "buddy_model": "test-model", "buddy_timeout": 0.5,
    })
    monkeypatch.setattr(buddy, "get_settings", lambda: settings)
    payloads = []

    async def pretend(request):
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-token"
        payloads.append(json.loads(request.content))
        with Session(postgres) as db:
            assert db.scalar(select(func.count()).select_from(BuddyMessage).where(BuddyMessage.status == "pending")) == 1
        if len(payloads) == 1:
            return httpx.Response(503)
        if len(payloads) == 4:
            await asyncio.sleep(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": f"Ответ {len(payloads)}"}}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(pretend), **kwargs,
    ))
    alice, boris = login("alisa"), login("boris")
    csrf = page_token(alice, "/buddy")
    first = str(uuid4())
    assert post(alice, "/buddy", csrf, request_id=first, question="Как спланировать переезд?").status_code == 303
    failure = alice.get("/buddy").text
    assert "Не удалось получить ответ" in failure and "Как спланировать переезд?" in failure
    assert post(boris, "/buddy", page_token(boris, "/buddy"), request_id=first, retry="1").status_code == 404
    assert "Как спланировать переезд?" not in boris.get("/buddy").text
    assert post(alice, "/buddy", csrf, request_id=first, retry="1").status_code == 303
    assert "Ответ 2" in alice.get("/buddy").text
    assert post(alice, "/buddy", csrf, request_id=first, question="Другой текст").status_code == 303
    assert len(payloads) == 2
    assert post(alice, "/buddy", csrf, request_id=str(uuid4()), question="А если я живу одна?").status_code == 303
    assert "Ответ 3" in alice.get("/buddy").text
    messages = payloads[-1]["messages"]
    assert payloads[-1]["model"] == "test-model"
    system = messages[0]["content"]
    for value in ("НИТУ МИСИС", "рисование", "Сокол", "23000", "Готовлюсь к переезду"):
        assert value in system
    for value in ("Алиса", "Борис", "alisa@", "МГУ", "test-token"):
        assert value not in system
    assert messages[1:] == [
        {"role": "user", "content": "Как спланировать переезд?"},
        {"role": "assistant", "content": "Ответ 2"},
        {"role": "user", "content": "А если я живу одна?"},
    ]
    assert post(alice, "/buddy", csrf, request_id=str(uuid4()), question="Проверка таймаута").status_code == 303
    assert "Не удалось получить ответ" in alice.get("/buddy").text
    assert alice.get("/neighbors").status_code == alice.get("/housing").status_code == 200


def test_buddy_without_key_preserves_question(postgres, monkeypatch):
    demo(postgres)
    monkeypatch.setattr(buddy, "get_settings", lambda: get_settings().model_copy(
        update={"buddy_api_key": SecretStr("")}
    ))
    alice = login("alisa")
    page = alice.get("/buddy").text
    assert "Buddy пока недоступен" in page
    assert post(alice, "/buddy", CSRF.search(page)[1], request_id=REQUEST_ID.search(page)[1],
                question="Что купить для общежития?").status_code == 303
    assert "Что купить для общежития?" in alice.get("/buddy").text
    assert alice.get("/housing").status_code == 200
