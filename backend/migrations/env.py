from alembic import context

from learnmarks.core.config import settings
from learnmarks.core.db import make_engine
from learnmarks.models import Base

target_metadata = Base.metadata


# Objects created with raw SQL in migrations (FTS5 tables, case-insensitive name indexes):
# autogenerate can't reflect them, so it must never try to drop or rebuild them.
RAW_SQL_OBJECTS = {"uq_tags_name", "uq_topics_name", "uq_topic_groups_name"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name and name.startswith("bookmark_fts"):
        return False
    if type_ == "index" and name in RAW_SQL_OBJECTS:
        return False
    return True


def run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                      include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    # CLI use (e.g. `alembic revision --autogenerate`): connect to the configured database.
    with make_engine(settings.db_path).begin() as conn:
        run_migrations(conn)
