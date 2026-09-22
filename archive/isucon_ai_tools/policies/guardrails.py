from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List


@dataclass
class Guardrails:
    allowlist_paths: List[str] = field(default_factory=lambda: ["/home/isucon", "/tmp", "/etc/nginx", "/etc/mysql"])
    deny_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /",
        "shutdown",
        "reboot",
        "dd if=/dev/zero",
    ])
    require_backup_before_write: bool = True
    require_score_before_after: bool = True
    max_retries_per_hypothesis: int = 2

    def is_allowed_path(self, path: str) -> bool:
        normalized_path = self._normalize_path(path)
        for prefix in self.allowlist_paths:
            normalized_prefix = self._normalize_path(prefix)
            if normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/"):
                return True
        return False

    def is_allowed_command(self, command: str) -> bool:
        return not any(block in command for block in self.deny_commands)

    def validate_path(self, path: str) -> str | None:
        if self.is_allowed_path(path):
            return None
        return f"Path is outside allowlist: {path}"

    def validate_command(self, command: str) -> str | None:
        if self.is_allowed_command(command):
            return None
        return f"Command is denied by guardrails: {command}"

    def _normalize_path(self, path: str) -> str:
        raw_parts = PurePosixPath(path).parts
        parts: List[str] = []
        absolute = path.startswith("/")
        for part in raw_parts:
            if part in ("", ".", "/"):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        prefix = "/" if absolute else ""
        return prefix + "/".join(parts)
