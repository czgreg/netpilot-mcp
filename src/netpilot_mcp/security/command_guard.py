"""命令安全控制：命令分级与拦截"""

import re
import json
import os
from enum import Enum
from dataclasses import dataclass


class SecurityLevel(Enum):
    """命令安全级别"""
    SAFE = "safe"               # 安全：直接执行
    SENSITIVE = "sensitive"     # 敏感：提示确认
    DANGEROUS = "dangerous"     # 危险：默认拒绝


@dataclass
class SecurityCheckResult:
    """安全检查结果"""
    level: SecurityLevel
    allowed: bool
    message: str


# 默认安全规则
DEFAULT_RULES: dict = {
    "dangerous_patterns": [
        r"^\s*reload\b",
        r"^\s*erase\b",
        r"^\s*delete\b",
        r"^\s*format\b",
        r"^\s*write\s+erase\b",
        r"^\s*reset\s+saved-configuration\b",
        r"^\s*restore\b",
    ],
    "sensitive_patterns": [
        r"^\s*configure\s+terminal\b",
        r"^\s*system-view\b",
        r"^\s*interface\b",
        r"^\s*ip\s+address\b",
        r"^\s*ip\s+route\b",
        r"^\s*router\b",
        r"^\s*no\s+",
        r"^\s*undo\s+",
        r"^\s*shutdown\b",
        r"^\s*switchport\b",
        r"^\s*vlan\b",
        r"^\s*port\s+",
        r"^\s*acl\b",
        r"^\s*snmp\b",
    ],
    "safe_patterns": [
        r"^\s*show\b",
        r"^\s*display\b",
        r"^\s*ping\b",
        r"^\s*traceroute\b",
        r"^\s*tracert\b",
        r"^\s*terminal\s+length\b",
        r"^\s*screen-length\b",
        r"^\s*enable\b",
        r"^\s*end\b",
        r"^\s*exit\b",
        r"^\s*return\b",
        r"^\s*quit\b",
        r"^\s*\?\s*$",
    ],
}


class CommandGuard:
    """命令安全控制器"""

    def __init__(self, rules: dict | None = None, enabled: bool = True):
        self.enabled = enabled
        rules = rules or DEFAULT_RULES
        self._dangerous = [re.compile(p, re.IGNORECASE) for p in rules.get("dangerous_patterns", [])]
        self._sensitive = [re.compile(p, re.IGNORECASE) for p in rules.get("sensitive_patterns", [])]
        self._safe = [re.compile(p, re.IGNORECASE) for p in rules.get("safe_patterns", [])]

    def check(self, command: str) -> SecurityCheckResult:
        """
        检查命令的安全级别。

        Returns:
            SecurityCheckResult 包含安全级别、是否允许执行、提示信息
        """
        if not self.enabled:
            return SecurityCheckResult(SecurityLevel.SAFE, True, "安全检查已禁用")

        cmd = command.strip()

        # 先检查危险命令
        for pattern in self._dangerous:
            if pattern.search(cmd):
                return SecurityCheckResult(
                    SecurityLevel.DANGEROUS,
                    False,
                    f"⛔ 危险命令被拦截: '{cmd}' 可能导致设备重启、数据丢失等严重后果。"
                    f"如需执行，请使用 device_execute 并添加 force=true 参数。"
                )

        # 检查安全命令
        for pattern in self._safe:
            if pattern.search(cmd):
                return SecurityCheckResult(SecurityLevel.SAFE, True, "")

        # 检查敏感命令
        for pattern in self._sensitive:
            if pattern.search(cmd):
                return SecurityCheckResult(
                    SecurityLevel.SENSITIVE,
                    True,
                    f"⚠️ 敏感命令: '{cmd}' 将修改设备配置，请确认后执行。"
                )

        # 默认允许（未匹配到任何规则）
        return SecurityCheckResult(SecurityLevel.SAFE, True, "")

    @classmethod
    def from_config_file(cls, path: str) -> "CommandGuard":
        """从 JSON 配置文件加载安全规则"""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                rules = json.load(f)
            return cls(rules=rules)
        return cls()
