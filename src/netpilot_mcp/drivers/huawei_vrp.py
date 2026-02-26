"""华为 VRP 设备驱动"""

from .base import BaseDriver, DeviceMode, PromptPattern


class HuaweiVRPDriver(BaseDriver):
    """华为 VRP 设备驱动"""

    DEVICE_TYPE = "huawei_vrp"
    DEVICE_VENDOR = "Huawei"

    @property
    def prompt_patterns(self) -> list[PromptPattern]:
        return [
            # 华为提示符: 用户视图 <Huawei>  系统视图 [Huawei]  接口视图 [Huawei-GE0/0/1]
            PromptPattern(DeviceMode.CONFIG_IF, r"\[\S+-\S+\]\s*$"),
            PromptPattern(DeviceMode.CONFIG, r"\[\S+\]\s*$"),
            PromptPattern(DeviceMode.USER, r"<\S+>\s*$"),
        ]

    def get_disable_paging_command(self) -> str:
        return "screen-length 0 temporary"

    def get_enter_enable_command(self) -> str:
        # 华为没有 enable，用户视图直接可以 system-view
        return ""

    def get_enter_config_command(self) -> str:
        return "system-view"

    def get_exit_config_command(self) -> str:
        return "return"

    def get_save_config_command(self) -> str:
        return "save force"

    def get_info_command(self, info_type: str) -> str:
        commands = {
            "version": "display version",
            "interfaces": "display ip interface brief",
            "routing": "display ip routing-table",
            "arp": "display arp",
            "all": "display version",
        }
        return commands.get(info_type, f"display {info_type}")

    def get_config_command(self, config_type: str, section: str = "") -> str:
        if config_type == "startup":
            cmd = "display saved-configuration"
        else:
            cmd = "display current-configuration"
        if section:
            cmd += f" | include {section}"
        return cmd

    def get_ping_command(self, target: str, count: int = 5, source: str = "") -> str:
        cmd = f"ping -c {count} {target}"
        if source:
            cmd += f" -a {source}"
        return cmd

    def get_traceroute_command(self, target: str) -> str:
        return f"tracert {target}"

    def detect_mode(self, prompt_text: str) -> DeviceMode:
        """华为设备模式检测：<> 为用户视图，[] 为系统/配置视图"""
        import re
        stripped = prompt_text.strip()
        last_line = stripped.split("\n")[-1].strip()

        if re.search(r"\[\S+-\S+\]\s*$", last_line):
            return DeviceMode.CONFIG_IF
        elif re.search(r"\[\S+\]\s*$", last_line):
            return DeviceMode.CONFIG
        elif re.search(r"<\S+>\s*$", last_line):
            return DeviceMode.USER
        return DeviceMode.UNKNOWN
