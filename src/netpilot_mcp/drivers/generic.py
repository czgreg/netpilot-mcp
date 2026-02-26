"""通用设备驱动：用于未被专门适配的设备"""

from .base import BaseDriver, DeviceMode, PromptPattern


class GenericDriver(BaseDriver):
    """
    通用设备驱动，提供最基本的提示符匹配。
    适用于未被专门适配的设备，或用户自定义设备。
    """

    DEVICE_TYPE = "generic"
    DEVICE_VENDOR = "Generic"

    @property
    def prompt_patterns(self) -> list[PromptPattern]:
        return [
            # 通用匹配：以 > 或 # 或 ] 或 $ 结尾
            PromptPattern(DeviceMode.CONFIG, r"\S+[#\]]\s*$"),
            PromptPattern(DeviceMode.USER, r"\S+[>$]\s*$"),
        ]

    def get_disable_paging_command(self) -> str:
        return "terminal length 0"

    def get_enter_enable_command(self) -> str:
        return "enable"

    def get_enter_config_command(self) -> str:
        return "configure terminal"

    def get_exit_config_command(self) -> str:
        return "end"

    def get_save_config_command(self) -> str:
        return "write memory"

    def get_info_command(self, info_type: str) -> str:
        commands = {
            "version": "show version",
            "interfaces": "show interface",
            "routing": "show ip route",
            "arp": "show arp",
            "all": "show version",
        }
        return commands.get(info_type, f"show {info_type}")

    def get_config_command(self, config_type: str, section: str = "") -> str:
        if config_type == "startup":
            return "show startup-config"
        return "show running-config"

    def get_ping_command(self, target: str, count: int = 5, source: str = "") -> str:
        return f"ping {target}"

    def get_traceroute_command(self, target: str) -> str:
        return f"traceroute {target}"
