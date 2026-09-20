from __future__ import annotations

from dataclasses import dataclass, field
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
        return any(path.startswith(prefix) for prefix in self.allowlist_paths)

    def is_allowed_command(self, command: str) -> bool:
        return not any(block in command for block in self.deny_commands)
