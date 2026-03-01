"""设备驱动抽象基类：定义多厂商设备适配的统一接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class DeviceMode(Enum):
    """设备操作模式"""
    UNKNOWN = "unknown"
    USER = "user"           # 用户模式 (>)
    PRIVILEGED = "privileged"  # 特权模式 (#)
    CONFIG = "config"       # 全局配置模式
    CONFIG_IF = "config_if"  # 接口配置模式
    CONFIG_ROUTER = "config_router"  # 路由配置模式
    CONFIG_SUB = "config_sub"  # 其他子配置模式


@dataclass
class PromptPattern:
    """提示符匹配模式"""
    mode: DeviceMode
    pattern: str  # 正则表达式


@dataclass
class DeviceInfo:
    """设备信息"""
    device_type: str = ""
    hostname: str = ""
    model: str = ""
    os_version: str = ""
    serial_number: str = ""


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool = True
    output: str = ""
    structured_output: dict | list | None = None
    structured_status: str = "unsupported"
    structured_parser: str = "none"
    device_mode: str = ""
    error: str = ""
    execution_time_ms: int = 0


class BaseDriver(ABC):
    """设备驱动抽象基类，所有厂商驱动需继承此类"""

    # 子类需设置
    DEVICE_TYPE: str = "generic"
    DEVICE_VENDOR: str = "Generic"

    @property
    @abstractmethod
    def prompt_patterns(self) -> list[PromptPattern]:
        """返回各模式下提示符的正则表达式列表（按优先级排序）"""
        pass

    @property
    def combined_prompt_pattern(self) -> str:
        """合并所有模式的提示符为一个正则表达式，用于 read_until_prompt"""
        patterns = [p.pattern for p in self.prompt_patterns]
        return "|".join(f"(?:{p})" for p in patterns)

    @abstractmethod
    def get_disable_paging_command(self) -> str:
        """返回禁用分页的命令"""
        pass

    @abstractmethod
    def get_enter_enable_command(self) -> str:
        """返回进入特权模式的命令"""
        pass

    @abstractmethod
    def get_enter_config_command(self) -> str:
        """返回进入全局配置模式的命令"""
        pass

    @abstractmethod
    def get_exit_config_command(self) -> str:
        """返回退出配置模式的命令"""
        pass

    @abstractmethod
    def get_save_config_command(self) -> str:
        """返回保存配置的命令"""
        pass

    @abstractmethod
    def get_info_command(self, info_type: str) -> str:
        """
        根据信息类型返回对应的查询命令。

        Args:
            info_type: version / interfaces / routing / arp

        Returns:
            对应的 show/display 命令
        """
        pass

    @abstractmethod
    def get_config_command(self, config_type: str, section: str = "") -> str:
        """
        返回查看配置的命令。

        Args:
            config_type: running / startup
            section: 配置段过滤

        Returns:
            对应命令
        """
        pass

    @abstractmethod
    def get_ping_command(self, target: str, count: int = 5, source: str = "") -> str:
        """返回 Ping 命令"""
        pass

    @abstractmethod
    def get_traceroute_command(self, target: str) -> str:
        """返回 Traceroute 命令"""
        pass

    def detect_mode(self, prompt_text: str) -> DeviceMode:
        """根据提示符文本检测当前设备模式"""
        import re
        for pp in self.prompt_patterns:
            if re.search(pp.pattern, prompt_text):
                return pp.mode
        return DeviceMode.UNKNOWN

    def extract_hostname(self, prompt_text: str) -> str:
        """从提示符中提取主机名"""
        import re
        # 通用提取：去掉提示符终结符后的部分
        stripped = prompt_text.strip()
        last_line = stripped.split("\n")[-1].strip()
        # 去掉 < > [ ] ( ) # > 等
        hostname = re.sub(r"[<>\[\]()#>]", "", last_line).strip()
        # 去掉 config 等后缀
        hostname = re.sub(r"[-_]?(config|configure).*", "", hostname, flags=re.IGNORECASE).strip()
        return hostname

    def clean_output(self, raw_output: str, command: str = "") -> str:
        """清洗输出：去除命令回显、控制字符、分页提示、末尾提示符等"""
        import re

        # 去除 ANSI 转义序列
        cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)
        # 去除 \r
        cleaned = cleaned.replace("\r", "")
        # 去除分页提示 （-- More --）等
        cleaned = re.sub(r"\s*--\s*[Mm]ore\s*--\s*", "", cleaned)

        # 去除命令回显（输出的第一行通常是命令本身）
        if command:
            lines = cleaned.split("\n")
            if lines and command.strip() in lines[0]:
                lines = lines[1:]
            cleaned = "\n".join(lines)

        # 去除末尾的设备提示符行（可能有多行）
        lines = cleaned.split("\n")
        while lines:
            last = lines[-1].strip()
            if not last:
                # 去除空行
                lines.pop()
                continue
            # 匹配常见提示符：Router#、Router>、Router(config)#、<Huawei>、[H3C]
            if re.match(r"^\S+[#>]\s*$", last) or \
               re.match(r"^\S+\(config[^)]*\)#\s*$", last) or \
               re.match(r"^<\S+>\s*$", last) or \
               re.match(r"^\[\S+[^\]]*\]\s*$", last):
                lines.pop()
                continue
            break

        return "\n".join(lines).strip()

    def is_long_running_command(self, command: str) -> bool:
        """判断是否为耗时命令（ping / traceroute 等）"""
        long_commands = [
            "ping",
            "traceroute",
            "tracert",
            "show tech",
            "display diagnostic",
            "show ip route",
            "display ip routing-table",
        ]
        cmd_lower = command.strip().lower()
        return any(cmd_lower.startswith(lc) for lc in long_commands)

    def get_long_running_timeout(self) -> int:
        """耗时命令的默认超时（毫秒）"""
        return 30000  # 30 秒
