"""create MVP schema

Revision: 337c041f6ccb
Revises: none
"""
import sqlalchemy as sa
from alembic import op


revision = '337c041f6ccb'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'housing_listings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('district', sa.String(length=80), nullable=False),
        sa.Column('metro', sa.String(length=80), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('total_rent', sa.Integer(), nullable=False),
        sa.Column('occupants', sa.Integer(), nullable=False),
        sa.Column('extras', sa.Integer(), nullable=False),
        sa.Column('allows_pets', sa.Boolean(), nullable=False),
        sa.Column('allows_smoking', sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('apartment', 'room')", name='listing_kind'),
        sa.CheckConstraint('total_rent > 0 AND occupants > 0 AND extras >= 0', name='listing_prices'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_table(
        'universities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'buddy_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'dormitories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('university_id', 'id'),
        sa.UniqueConstraint('university_id', 'name'),
    )
    op.create_table(
        'favorites',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('listing_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['listing_id'], ['housing_listings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'listing_id'),
    )
    op.create_table(
        'matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_id', sa.Integer(), nullable=False),
        sa.Column('second_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('first_id < second_id', name='match_canonical_order'),
        sa.ForeignKeyConstraint(['first_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['second_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('first_id', 'second_id'),
    )
    op.create_index('ix_matches_second_id', 'matches', ['second_id'], unique=False)
    op.create_table(
        'swipes',
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=4), nullable=False),
        sa.CheckConstraint("action IN ('like', 'skip')", name='swipe_action'),
        sa.CheckConstraint('actor_id <> target_id', name='swipe_distinct_users'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('actor_id', 'target_id'),
    )
    op.create_table(
        'buddy_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(length=36), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'answered', 'failed')", name='buddy_message_status'),
        sa.ForeignKeyConstraint(['conversation_id'], ['buddy_conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'request_id'),
    )
    op.create_table(
        'profiles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=80), nullable=False),
        sa.Column('mode', sa.String(length=8), nullable=False),
        sa.Column('district', sa.String(length=80), nullable=True),
        sa.Column('university_id', sa.Integer(), nullable=True),
        sa.Column('dormitory_id', sa.Integer(), nullable=True),
        sa.Column('dorm_scope', sa.String(length=12), nullable=False),
        sa.Column('budget_min', sa.Integer(), nullable=True),
        sa.Column('budget_max', sa.Integer(), nullable=True),
        sa.Column('smokes', sa.Boolean(), nullable=True),
        sa.Column('allows_smoking', sa.Boolean(), nullable=True),
        sa.Column('has_pet', sa.Boolean(), nullable=True),
        sa.Column('allows_pets', sa.Boolean(), nullable=True),
        sa.Column('interests', sa.String(length=240), nullable=True),
        sa.Column('move_stage', sa.String(length=40), nullable=True),
        sa.CheckConstraint("dorm_scope IN ('dormitory', 'university')", name='profile_dorm_scope'),
        sa.CheckConstraint("mode IN ('rent', 'dorm')", name='profile_mode'),
        sa.CheckConstraint('(budget_min IS NULL AND budget_max IS NULL) OR (budget_min IS NOT NULL AND budget_max IS NOT NULL AND budget_min > 0 AND budget_max >= budget_min)', name='profile_budget'),
        sa.CheckConstraint('dormitory_id IS NULL OR university_id IS NOT NULL', name='profile_dorm_university'),
        sa.ForeignKeyConstraint(['university_id', 'dormitory_id'], ['dormitories.university_id', 'dormitories.id']),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'preferences',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('sleep', sa.String(length=12), nullable=True),
        sa.Column('cleaning', sa.Integer(), nullable=True),
        sa.Column('guests', sa.Integer(), nullable=True),
        sa.Column('noise', sa.Integer(), nullable=True),
        sa.Column('cooking', sa.Integer(), nullable=True),
        sa.Column('sociability', sa.Integer(), nullable=True),
        sa.CheckConstraint("sleep IN ('early', 'flexible', 'late')", name='preference_sleep'),
        sa.CheckConstraint('cleaning BETWEEN 1 AND 5', name='preference_cleaning'),
        sa.CheckConstraint('cooking BETWEEN 1 AND 5', name='preference_cooking'),
        sa.CheckConstraint('guests BETWEEN 1 AND 5', name='preference_guests'),
        sa.CheckConstraint('noise BETWEEN 1 AND 5', name='preference_noise'),
        sa.CheckConstraint('sociability BETWEEN 1 AND 5', name='preference_sociability'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade():
    op.drop_table('preferences')
    op.drop_table('profiles')
    op.drop_table('buddy_messages')
    op.drop_table('swipes')
    op.drop_index('ix_matches_second_id', table_name='matches')
    op.drop_table('matches')
    op.drop_table('favorites')
    op.drop_table('dormitories')
    op.drop_table('buddy_conversations')
    op.drop_table('users')
    op.drop_table('universities')
    op.drop_table('housing_listings')
