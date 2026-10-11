import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("LEARNMARKS_DATA_DIR", REPO_ROOT / "data")))
    port: int = int(os.environ.get("LEARNMARKS_PORT", "8000"))
    web_dist: Path = REPO_ROOT / "web" / "dist"
    # Extra Host/Origin values accepted on top of 127.0.0.1/localhost:<port> (e.g. the Vite dev server).
    extra_hosts: tuple[str, ...] = ("127.0.0.1:5173", "localhost:5173")
    # The phone reaches the laptop at 127.0.0.1:<sync_port> through `adb reverse` (DESIGN §8).
    sync_port: int = int(os.environ.get("LEARNMARKS_SYNC_PORT", "8765"))
    adb_path: str | None = os.environ.get("LEARNMARKS_ADB")
    # Take a daily backup in the background while the server runs (off in tests).
    auto_backup: bool = os.environ.get("LEARNMARKS_AUTO_BACKUP", "1") != "0"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "learnmarks.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"127.0.0.1:{self.sync_port}", *self.extra_hosts}


settings = Settings()
