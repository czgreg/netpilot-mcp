"""输出解析工具"""

import re


class OutputParser:
    """设备输出解析与清洗"""

    @staticmethod
    def remove_ansi_codes(text: str) -> str:
        """移除 ANSI 转义序列"""
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    @staticmethod
    def remove_carriage_returns(text: str) -> str:
        """移除回车符"""
        return text.replace("\r", "")

    @staticmethod
    def remove_more_prompts(text: str) -> str:
        """移除分页提示符 (-- More --)"""
        return re.sub(r"\s*--\s*[Mm]ore\s*--\s*", "", text)

    @staticmethod
    def remove_command_echo(text: str, command: str) -> str:
        """移除命令回显（输出的第一行）"""
        if not command:
            return text
        lines = text.split("\n")
        if lines and command.strip() in lines[0]:
            lines = lines[1:]
        return "\n".join(lines)

    @staticmethod
    def remove_trailing_prompt(text: str) -> str:
        """移除输出末尾的设备提示符"""
        lines = text.strip().split("\n")
        if not lines:
            return text

        last_line = lines[-1].strip()
        # 检查最后一行是否为提示符
        if re.search(r"^[\S]+[>#\]$]\s*$", last_line):
            lines = lines[:-1]

        return "\n".join(lines)

    @classmethod
    def clean(cls, raw_output: str, command: str = "") -> str:
        """完整的输出清洗流程"""
        text = cls.remove_ansi_codes(raw_output)
        text = cls.remove_carriage_returns(text)
        text = cls.remove_more_prompts(text)
        if command:
            text = cls.remove_command_echo(text, command)
        text = cls.remove_trailing_prompt(text)
        return text.strip()
