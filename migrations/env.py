from alembic import context

from dormbuddy import models
from dormbuddy.config import get_settings
from dormbuddy.db import get_engine

if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=models.Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=models.Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
