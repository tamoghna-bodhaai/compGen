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

    def get(self, profile_id: str) -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM branding_profiles WHERE id = ?", (profile_id,)).fetchone()
        return {**dict(row), "branding_config": json.loads(row["branding_config"])} if row else None

    def update(self, profile_id: str, name: str, branding_config: dict[str, Any]) -> dict[str, Any] | None:
        now = _now()
        with get_connection() as connection:
            cursor = connection.execute(
                "UPDATE branding_profiles SET name = ?, branding_config = ?, updated_at = ? WHERE id = ?",
                (name.strip(), json.dumps(branding_config), now, profile_id),
            )
            if cursor.rowcount != 1:
                return None
        return self.get(profile_id)

    def duplicate(self, profile_id: str) -> dict[str, Any] | None:
        profile = self.get(profile_id)
        if profile is None:
            return None
        base, name, index = f"{profile['name']} copy", f"{profile['name']} copy", 2
        existing = {item["name"].lower() for item in self.list()}
        while name.lower() in existing:
            name = f"{base} {index}"
            index += 1
        return self.save(name, profile["branding_config"])

    def delete(self, profile_id: str) -> bool:
        with get_connection() as connection:
            return connection.execute("DELETE FROM branding_profiles WHERE id = ?", (profile_id,)).rowcount == 1

    def resolve(self, profile_id: str | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
        profile = self.get(profile_id) if profile_id else None
        return {**(profile["branding_config"] if profile else {}), **(overrides or {})}
