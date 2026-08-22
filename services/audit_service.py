"""Append-only audit trail with JSON persistence and per-order records."""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.schemas import AuditEntry, OrchestrationResult

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._orders_dir = storage_dir / "orders"
        self._orders_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = storage_dir / "audit_log.json"
        self._lock = threading.Lock()

    def log(self, order_id: str, agent: str, action: str, status: str, message: str) -> AuditEntry:
        entry = AuditEntry(
            timestamp_utc=datetime.now(timezone.utc),
            order_id=order_id,
            agent=agent,
            action=action,
            status=status,
            message=message,
        )
        self._append(entry)
        logger.info(
            "order=%s agent=%s action=%s status=%s message=%s",
            order_id,
            agent,
            action,
            status,
            message,
        )
        return entry

    def persist_order(self, result: OrchestrationResult) -> None:
        path = self._orders_dir / f"{result.order_id}.json"
        with self._lock:
            path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Persisted order record %s to %s", result.order_id, path)

    def get_order(self, order_id: str) -> Optional[OrchestrationResult]:
        path = self._orders_dir / f"{order_id}.json"
        if not path.exists():
            return None
        try:
            return OrchestrationResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.error("Failed to load order %s: %s", order_id, exc)
            return None

    def get_entries(self, order_id: str) -> list[AuditEntry]:
        return [entry for entry in self._read_log() if entry.order_id == order_id]

    def _append(self, entry: AuditEntry) -> None:
        entries = self._read_log()
        entries.append(entry)
        payload = json.dumps(
            [item.model_dump(mode="json") for item in entries],
            indent=2,
        )
        with self._lock:
            self._log_path.write_text(payload, encoding="utf-8")

    def _read_log(self) -> list[AuditEntry]:
        if not self._log_path.exists():
            return []
        try:
            raw = json.loads(self._log_path.read_text(encoding="utf-8"))
            return [AuditEntry.model_validate(item) for item in raw]
        except (OSError, ValueError) as exc:
            logger.error("Audit log unreadable, starting fresh: %s", exc)
            return []
