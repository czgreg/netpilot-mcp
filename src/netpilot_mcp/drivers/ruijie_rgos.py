"""锐捷 RGOS 设备驱动"""

from .base import BaseDriver, DeviceMode, PromptPattern


class RuijieRGOSDriver(BaseDriver):
    """锐捷 RGOS 设备驱动（CLI 风格类似 Cisco IOS）"""

    DEVICE_TYPE = "ruijie_rgos"
    DEVICE_VENDOR = "Ruijie"

    @property
    def prompt_patterns(self) -> list[PromptPattern]:
        return [
            PromptPattern(DeviceMode.CONFIG_IF, r"\S+\(config-if\)#\s*$"),
            PromptPattern(DeviceMode.CONFIG_ROUTER, r"\S+\(config-router\)#\s*$"),
            PromptPattern(DeviceMode.CONFIG_SUB, r"\S+\(config-\S+\)#\s*$"),
            PromptPattern(DeviceMode.CONFIG, r"\S+\(config\)#\s*$"),
            PromptPattern(DeviceMode.PRIVILEGED, r"\S+#\s*$"),
            PromptPattern(DeviceMode.USER, r"\S+>\s*$"),
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
        return "write"

    def get_info_command(self, info_type: str) -> str:
        commands = {
            "version": "show version",
            "interfaces": "show ip interface brief",
            "routing": "show ip route",
            "arp": "show arp",
            "all": "show version",
        }
        return commands.get(info_type, f"show {info_type}")

    def get_config_command(self, config_type: str, section: str = "") -> str:
        if config_type == "startup":
            cmd = "show startup-config"
        else:
            cmd = "show running-config"
        if section:
            cmd += f" | include {section}"
        return cmd

    def get_ping_command(self, target: str, count: int = 5, source: str = "") -> str:
        cmd = f"ping {target} count {count}"
        if source:
            cmd += f" source {source}"
        return cmd

    def get_traceroute_command(self, target: str) -> str:
        return f"traceroute {target}"
