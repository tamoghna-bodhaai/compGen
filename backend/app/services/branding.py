from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.database import get_connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


class BrandingProfileService:
    def list(self) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute("SELECT * FROM branding_profiles ORDER BY updated_at DESC, name COLLATE NOCASE").fetchall()
        return [{**dict(row), "branding_config": json.loads(row["branding_config"])} for row in rows]

    def save(self, name: str, branding_config: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO branding_profiles (id, name, branding_config, created_at, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET branding_config = excluded.branding_config, updated_at = excluded.updated_at",
                (str(uuid.uuid4()), name.strip(), json.dumps(branding_config), now, now),
            )
            row = connection.execute("SELECT * FROM branding_profiles WHERE name = ?", (name.strip(),)).fetchone()
        return {**dict(row), "branding_config": json.loads(row["branding_config"])}
