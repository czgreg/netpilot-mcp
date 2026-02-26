"""提示符检测工具"""

import re
from ..drivers.base import DeviceMode


class PromptDetector:
    """通用提示符检测器"""

    @staticmethod
    def detect_prompt_in_text(text: str) -> str | None:
        """从文本中提取最后一行的提示符"""
        if not text or not text.strip():
            return None

        last_line = text.strip().split("\n")[-1].strip()

        # 常见提示符模式
        patterns = [
            r"\S+\(config[^)]*\)#\s*$",  # Cisco/锐捷 配置模式
            r"\S+#\s*$",                   # Cisco/锐捷 特权模式
            r"\S+>\s*$",                   # Cisco/锐捷 用户模式
            r"<\S+>\s*$",                  # 华为/H3C 用户视图
            r"\[\S+[^\]]*\]\s*$",          # 华为/H3C 系统视图
        ]

        for pattern in patterns:
            if re.search(pattern, last_line):
                return last_line

        return None

    @staticmethod
    def looks_like_prompt(text: str) -> bool:
        """快速判断文本末尾是否像提示符"""
        if not text or not text.strip():
            return False
        last_char = text.strip()[-1]
        return last_char in ">#]$"
