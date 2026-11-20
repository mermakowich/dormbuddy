import os

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .auth import passwords
from .db import get_engine
from .models import Dormitory, Favorite, HousingListing, Preferences, Profile, University, User

LISTINGS = [
    dict(
        slug="sokol-apartment", title="Двухкомнатная у Сокола", district="Сокол", metro="Сокол",
        kind="apartment", total_rent=60_000, occupants=2, extras=4_800,
        allows_pets=True, allows_smoking=False,
        description="Две изолированные комнаты и общая кухня. Доля рассчитана на двух жильцов.",
    ),
    dict(
        slug="academ-room", title="Комната на Академической", district="Академический", metro="Академическая",
        kind="room", total_rent=25_000, occupants=1, extras=2_000,
        allows_pets=False, allows_smoking=False,
        description="Отдельная комната в общей квартире. Кухня и санузел общие.",
    ),
    dict(
        slug="izmaylovo-apartment", title="Квартира в Измайлове", district="Измайлово", metro="Первомайская",
        kind="apartment", total_rent=66_000, occupants=3, extras=5_700,
        allows_pets=True, allows_smoking=False,
        description="Три комнаты. Стоимость доли рассчитана для троих.",
    ),
    dict(
        slug="sokol-room", title="Комната у Сокола", district="Сокол", metro="Аэропорт",
        kind="room", total_rent=30_000, occupants=1, extras=2_300,
        allows_pets=False, allows_smoking=True,
        description="Комната на одного жильца. В учебном примере курение допустимо.",
    ),
    dict(
        slug="lefortovo-apartment", title="Двухкомнатная в Лефортове", district="Лефортово", metro="Лефортово",
        kind="apartment", total_rent=69_000, occupants=2, extras=6_000,
        allows_pets=False, allows_smoking=False,
        description="Две комнаты и общая гостиная. Дополнительные расходы указаны на всю квартиру.",
    ),
]


def ensure(db, model, keys, values):
    statement = insert(model).values(**values).on_conflict_do_nothing(index_elements=keys).returning(model.id)
    new_id = db.scalar(statement)
    if new_id is not None:
        return new_id, True
    return db.scalar(select(model.id).filter_by(**{key: values[key] for key in keys})), False


def seed(db: Session, password: str):
    misis, _ = ensure(db, University, ["name"], {"name": "НИТУ МИСИС"})
    mgu, _ = ensure(db, University, ["name"], {"name": "МГУ"})
    dormitories = [
        ensure(db, Dormitory, ["university_id", "name"], {"university_id": university, "name": name})[0]
        for university, name in [(misis, "Общежитие № 1"), (misis, "Общежитие № 2"), (mgu, "Учебное общежитие")]
    ]
    listings = {row["slug"]: ensure(db, HousingListing, ["slug"], row)[0] for row in LISTINGS}

    rent = {"mode": "rent", "district": "Сокол", "budget_min": 23_000, "budget_max": 32_000}
    dorm = {"mode": "dorm", "university_id": misis, "dormitory_id": dormitories[0]}
    regular = {"sleep": "early", "cleaning": 4, "guests": 2, "noise": 2, "cooking": 3, "sociability": 4}
    users = [
        ("alisa", "Алиса", rent | {"university_id": misis, "move_stage": "packing", "interests": "рисование"}, regular,
         ["sokol-apartment", "academ-room"]),
        ("boris", "Борис", rent | {"university_id": mgu, "budget_min": 27_000, "budget_max": 33_000},
         regular | {"cleaning": 2, "guests": 3}, ["sokol-apartment", "izmaylovo-apartment"]),
        ("vera", "Вера", rent | {"smokes": True}, regular, []),
        ("artem", "Артём", rent | {"budget_min": 40_000, "budget_max": 45_000}, regular, []),
        ("mila", "Мила", rent, {}, []),
        ("nadya", "Надя", dorm, regular, []),
        ("oleg", "Олег", dorm | {"dorm_scope": "university"}, regular | {"cooking": 4}, []),
        ("sonya", "Соня", dorm | {"dormitory_id": dormitories[1], "dorm_scope": "university"}, regular, []),
        ("timur", "Тимур", dorm | {"university_id": mgu, "dormitory_id": dormitories[2]}, regular, []),
    ]
    for login, name, context, preferences, favorites in users:
        email = f"{login}@example.com"
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            continue
        user_id, created = ensure(db, User, ["email"], {"email": email, "password_hash": passwords.hash(password)})
        if not created:
            continue
        habits = {"smokes": False, "allows_smoking": False, "has_pet": False, "allows_pets": True}
        db.add(Profile(user_id=user_id, display_name=name, preferences=Preferences(**preferences), **(habits | context)))
        db.add_all(Favorite(user_id=user_id, listing_id=listings[slug]) for slug in favorites)
    db.commit()


if __name__ == "__main__":
    demo_password = os.environ.get("DORMBUDDY_DEMO_PASSWORD", "")
    if not 10 <= len(demo_password) <= 128:
        raise SystemExit("Set DORMBUDDY_DEMO_PASSWORD to a local demo password (10–128 characters).")
    with Session(get_engine()) as session:
        seed(session, demo_password)
    print("Демонстрационные справочники, анкеты и объявления готовы.")
