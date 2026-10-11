"""Development only: fill a throwaway database from ai-learning-path/path.json.

The real importer (dry run, progress, idempotent re-import) is Phase 2.
Usage: LEARNMARKS_DATA_DIR=../data-dev uv run python scripts/seed_dev.py ../../ai-learning-path/path.json
"""

import json
import random
import sys
from datetime import date
from pathlib import Path

from learnmarks.core.config import settings
from learnmarks.core.db import get_session, init_db
from learnmarks.schemas import BookmarkCreate, GroupCreate, TopicCreate
from learnmarks.services import bookmarks, topics

PALETTE = ["#C9CDBB", "#E9C9C3", "#EFD98A", "#BCC6D6", "#D5C6E6", "#A9CCC9", "#E6D3B8", "#D9D9DC"]
STATUSES = ["saved", "to_learn", "to_learn", "in_progress", "learned"]


def main(path: str) -> None:
    data = json.loads(Path(path).read_text())
    init_db(settings.db_path)
    session = next(get_session())
    rnd = random.Random(7)
    n = 0
    for track in data["tracks"]:
        group = topics.create_group(session, GroupCreate(name=track["name"]))
        for i, module in enumerate(track["modules"]):
            level = module.get("level") if module.get("level") in ("beginner", "intermediate", "advanced", "any") else None
            topic = topics.create_topic(session, TopicCreate(name=module["name"], description=module.get("why"),
                                                             color=PALETTE[i % len(PALETTE)], group_id=group.id, level=level))
            for item in module["items"]:
                bookmarks.create(session, BookmarkCreate(
                    url=f"https://x.com/{item['handle']}/status/{item['id']}",
                    title=item["title"][:300],
                    date_saved=date.fromisoformat(item["date"]),
                    description=" ".join(x for x in (item.get("summary"), item.get("learn")) if x)[:2000] or None,
                    status=rnd.choice(STATUSES),  # sample statuses: real progress comes with the Phase 2 import
                    priority=rnd.choice([1, 2, 2, 3]),
                    topic_ids=[topic.id],
                    tag_names=[t for t in (item.get("level"), item.get("kind")) if t],
                ))
                n += 1
    session.commit()
    print(f"seeded {n} bookmarks into {settings.db_path}")


if __name__ == "__main__":
    main(sys.argv[1])
