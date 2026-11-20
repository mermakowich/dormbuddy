from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    profile: Mapped["Profile"] = relationship(back_populates="user")


class University(Base):
    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    dormitories: Mapped[list["Dormitory"]] = relationship(order_by="Dormitory.name")


class Dormitory(Base):
    __tablename__ = "dormitories"
    __table_args__ = (UniqueConstraint("university_id", "name"), UniqueConstraint("university_id", "id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey("universities.id"))
    name: Mapped[str] = mapped_column(String(120))


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        ForeignKeyConstraint(["university_id", "dormitory_id"], ["dormitories.university_id", "dormitories.id"]),
        CheckConstraint("mode IN ('rent', 'dorm')", name="profile_mode"),
        CheckConstraint("dorm_scope IN ('dormitory', 'university')", name="profile_dorm_scope"),
        CheckConstraint("dormitory_id IS NULL OR university_id IS NOT NULL", name="profile_dorm_university"),
        CheckConstraint(
            "(budget_min IS NULL AND budget_max IS NULL) OR "
            "(budget_min IS NOT NULL AND budget_max IS NOT NULL AND budget_min > 0 AND budget_max >= budget_min)",
            name="profile_budget",
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    mode: Mapped[str] = mapped_column(String(8), default="rent")
    district: Mapped[str | None] = mapped_column(String(80))
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id"))
    dormitory_id: Mapped[int | None]
    dorm_scope: Mapped[str] = mapped_column(String(12), default="dormitory")
    budget_min: Mapped[int | None]
    budget_max: Mapped[int | None]
    smokes: Mapped[bool | None]
    allows_smoking: Mapped[bool | None]
    has_pet: Mapped[bool | None]
    allows_pets: Mapped[bool | None]
    interests: Mapped[str | None] = mapped_column(String(240))
    move_stage: Mapped[str | None] = mapped_column(String(40))

    user: Mapped[User] = relationship(back_populates="profile")
    university: Mapped[University | None] = relationship(foreign_keys=[university_id])
    dormitory: Mapped[Dormitory | None] = relationship(
        primaryjoin="and_(Profile.dormitory_id == Dormitory.id, Profile.university_id == Dormitory.university_id)",
        viewonly=True,
    )
    preferences: Mapped["Preferences"] = relationship(back_populates="profile")


class Preferences(Base):
    __tablename__ = "preferences"
    __table_args__ = (
        CheckConstraint("sleep IN ('early', 'flexible', 'late')", name="preference_sleep"),
        CheckConstraint("cleaning BETWEEN 1 AND 5", name="preference_cleaning"),
        CheckConstraint("guests BETWEEN 1 AND 5", name="preference_guests"),
        CheckConstraint("noise BETWEEN 1 AND 5", name="preference_noise"),
        CheckConstraint("cooking BETWEEN 1 AND 5", name="preference_cooking"),
        CheckConstraint("sociability BETWEEN 1 AND 5", name="preference_sociability"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True)
    sleep: Mapped[str | None] = mapped_column(String(12))
    cleaning: Mapped[int | None]
    guests: Mapped[int | None]
    noise: Mapped[int | None]
    cooking: Mapped[int | None]
    sociability: Mapped[int | None]

    profile: Mapped[Profile] = relationship(back_populates="preferences")


class Swipe(Base):
    __tablename__ = "swipes"
    __table_args__ = (
        CheckConstraint("actor_id <> target_id", name="swipe_distinct_users"),
        CheckConstraint("action IN ('like', 'skip')", name="swipe_action"),
    )

    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    action: Mapped[str] = mapped_column(String(4))


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("first_id", "second_id"),
        CheckConstraint("first_id < second_id", name="match_canonical_order"),
        Index("ix_matches_second_id", "second_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    second_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HousingListing(Base):
    __tablename__ = "housing_listings"
    __table_args__ = (
        CheckConstraint("kind IN ('apartment', 'room')", name="listing_kind"),
        CheckConstraint("total_rent > 0 AND occupants > 0 AND extras >= 0", name="listing_prices"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    district: Mapped[str] = mapped_column(String(80))
    metro: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text)
    total_rent: Mapped[int]
    occupants: Mapped[int]
    extras: Mapped[int]
    allows_pets: Mapped[bool]
    allows_smoking: Mapped[bool]


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("housing_listings.id", ondelete="CASCADE"), primary_key=True)


class BuddyConversation(Base):
    __tablename__ = "buddy_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)


class BuddyMessage(Base):
    __tablename__ = "buddy_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id"),
        CheckConstraint("status IN ('pending', 'answered', 'failed')", name="buddy_message_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("buddy_conversations.id", ondelete="CASCADE"))
    request_id: Mapped[str] = mapped_column(String(36))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8))
    attempt: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
