from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import BigInteger, cast, delete, select
from sqlalchemy.dialects.postgresql import insert

from .models import Favorite, HousingListing, Match, Profile
from .swipes import RecordId, membership
from .web import DB, CurrentUser, Form, read_int, redirect, render

router = APIRouter()
KINDS = {"apartment": "Квартира", "room": "Комната"}
FILTERS = ("minimum", "maximum", "location", "kind", "pets", "smoking")


def listing_page(request, user, listings, favorite_ids, **context):
    return render(
        request, "housing.html", user=user, listings=listings, favorites=favorite_ids,
        kinds=KINDS, share=share, **context,
    )


def share(listing):
    return Decimal(listing.total_rent) / listing.occupants


@router.get("/housing")
def housing(request: Request, db: DB, user: CurrentUser):
    values = {key: request.query_params.get(key, "").strip() for key in FILTERS}
    errors = {}
    minimum = read_int(values, "minimum", 1, 1_000_000, errors, "Укажи целое число от 1 до 1 000 000.")
    maximum = read_int(values, "maximum", 1, 1_000_000, errors, "Укажи целое число от 1 до 1 000 000.")
    if minimum is not None and maximum is not None and minimum > maximum:
        errors["maximum"] = "Верхняя граница должна быть не меньше нижней."
    if len(values["location"]) > 80 or "\0" in values["location"]:
        errors["location"] = "Район или метро — до 80 символов."
    if values["kind"] and values["kind"] not in KINDS:
        errors["kind"] = "Выбери тип из списка."
    for key in ("pets", "smoking"):
        if values[key] not in {"", "yes", "no"}:
            errors[key] = "Выбери «Да», «Нет» или «Неважно»."

    query = select(HousingListing).order_by(HousingListing.id)
    occupants = cast(HousingListing.occupants, BigInteger)
    if minimum is not None:
        query = query.where(HousingListing.total_rent >= minimum * occupants)
    if maximum is not None:
        query = query.where(HousingListing.total_rent <= maximum * occupants)
    if location := values["location"]:
        query = query.where(
            HousingListing.district.icontains(location, autoescape=True)
            | HousingListing.metro.icontains(location, autoescape=True)
        )
    if values["kind"]:
        query = query.where(HousingListing.kind == values["kind"])
    for key, column in [("pets", HousingListing.allows_pets), ("smoking", HousingListing.allows_smoking)]:
        if values[key]:
            query = query.where(column.is_(values[key] == "yes"))
    favorites = set(db.scalars(select(Favorite.listing_id).where(Favorite.user_id == user.id)))
    return listing_page(
        request, user, [] if errors else db.scalars(query).all(), favorites, view="feed",
        values=values, errors=errors, status=422 if errors else 200,
        current_query=urlencode({key: value for key, value in values.items() if value}),
    )


@router.get("/housing/favorites")
def favorites(request: Request, db: DB, user: CurrentUser):
    listings = db.scalars(select(HousingListing).join(Favorite).where(
        Favorite.user_id == user.id
    ).order_by(HousingListing.id)).all()
    return listing_page(request, user, listings, {listing.id for listing in listings}, view="favorites")


@router.get("/housing/{listing_id}")
def listing_detail(listing_id: RecordId, request: Request, db: DB, user: CurrentUser):
    listing = db.get(HousingListing, listing_id)
    if listing is None:
        raise HTTPException(404)
    return render(
        request, "listing.html", user=user, listing=listing, kinds=KINDS, share=share,
        favorites={listing_id} if db.get(Favorite, (user.id, listing_id)) else set(),
    )


@router.post("/housing/{listing_id}/favorite")
def change_favorite(listing_id: RecordId, request: Request, db: DB, user: CurrentUser, form: Form):
    if db.get(HousingListing, listing_id) is None:
        raise HTTPException(404)
    action = form.get("action")
    if action == "add":
        db.execute(insert(Favorite).values(user_id=user.id, listing_id=listing_id).on_conflict_do_nothing(
            index_elements=[Favorite.user_id, Favorite.listing_id]
        ))
    elif action == "remove":
        db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.listing_id == listing_id))
    else:
        raise HTTPException(400, "Выбери действие с избранным.")
    db.commit()

    source = form.get("source")
    if source == "favorites":
        return redirect("/housing/favorites")
    if source == "feed":
        query = urlencode([
            (key, request.query_params[key]) for key in FILTERS if request.query_params.get(key)
        ])
        return redirect("/housing" + ("?" + query if query else ""))
    return redirect(f"/housing/{listing_id}")


@router.get("/matches/{match_id}/housing")
def shared_housing(match_id: RecordId, request: Request, db: DB, user: CurrentUser):
    match = db.scalar(select(Match).where(Match.id == match_id, membership(user.id)))
    if match is None:
        raise HTTPException(404)
    other_id = match.second_id if match.first_id == user.id else match.first_id
    name = db.get(Profile, other_id).display_name
    other_favorites = select(Favorite.listing_id).where(Favorite.user_id == other_id)
    listings = db.scalars(select(HousingListing).join(Favorite).where(
        Favorite.user_id == user.id, HousingListing.id.in_(other_favorites),
    ).order_by(HousingListing.id)).all()
    return listing_page(request, user, listings, set(), view="shared", partner=name)
