"""结构化输出解析器（面向大模型消费）"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class StructuredResult:
    """结构化解析结果"""

    status: str
    parser: str
    data: Any
    message: str = ""


class StructuredOutputParser:
    """针对常见网络命令输出生成结构化 JSON"""

    @classmethod
    def parse(cls, command: str, output: str, device_type: str = "generic") -> StructuredResult:
        cmd = " ".join(command.strip().lower().split())
        if not output.strip():
            return StructuredResult(status="empty", parser="none", data=None, message="输出为空")

        ntc = cls._parse_with_ntc(device_type=device_type, command=command, output=output)
        if ntc is not None:
            return ntc

        # Cisco/Ruijie
        if cmd.startswith("show ip interface brief"):
            data = cls._parse_show_ip_interface_brief(output)
            if data is not None:
                return StructuredResult(status="ok", parser="show_ip_interface_brief", data=data)

        if cmd.startswith("show version") or cmd.startswith("display version"):
            data = cls._parse_version(output)
            if data is not None:
                return StructuredResult(status="ok", parser="version", data=data)

        if cmd.startswith("show ip route") or cmd.startswith("display ip routing-table"):
            data = cls._parse_routes(output)
            if data is not None:
                return StructuredResult(status="ok", parser="routes", data=data)

        if cmd.startswith("show arp") or cmd.startswith("display arp"):
            data = cls._parse_arp(output)
            if data is not None:
                return StructuredResult(status="ok", parser="arp", data=data)

        # Huawei/H3C
        if cmd.startswith("display ip interface brief"):
            data = cls._parse_display_ip_interface_brief(output)
            if data is not None:
                return StructuredResult(status="ok", parser="display_ip_interface_brief", data=data)

        # fallback
        return StructuredResult(status="unsupported", parser="none", data=None, message="未命中结构化模板")

    @classmethod
    def _parse_with_ntc(cls, device_type: str, command: str, output: str) -> StructuredResult | None:
        try:
            from ntc_templates.parse import parse_output
        except Exception:
            return None

        platforms = cls._ntc_platform_candidates(device_type)
        for platform in platforms:
            try:
                parsed = parse_output(
                    platform=platform,
                    command=command,
                    data=output,
                    try_fallback=True,
                )
                if parsed:
                    return StructuredResult(
                        status="ok",
                        parser=f"ntc_templates.{platform}",
                        data={"count": len(parsed), "items": parsed},
                    )
            except Exception:
                continue
        return None

    @staticmethod
    def _ntc_platform_candidates(device_type: str) -> list[str]:
        mapping = {
            "cisco_ios": ["cisco_ios"],
            "huawei_vrp": ["huawei"],
            "h3c_comware": ["hp_comware"],
            "ruijie_rgos": ["ruijie_os", "cisco_ios"],
            "generic": ["cisco_ios", "huawei", "hp_comware"],
        }
        return mapping.get(device_type, ["cisco_ios", "huawei", "hp_comware"])

    @staticmethod
    def _split_non_empty_lines(text: str) -> list[str]:
        return [ln.rstrip() for ln in text.splitlines() if ln.strip()]

    @classmethod
    def _parse_show_ip_interface_brief(cls, output: str) -> dict[str, Any] | None:
        lines = cls._split_non_empty_lines(output)
        hdr_idx = -1
        for idx, ln in enumerate(lines):
            if "interface" in ln.lower() and "protocol" in ln.lower():
                hdr_idx = idx
                break
        if hdr_idx < 0:
            return None

        records: list[dict[str, str]] = []
        for ln in lines[hdr_idx + 1 :]:
            parts = ln.split()
            if len(parts) < 6:
                continue
            # Cisco 常见格式: Interface IP-Address OK? Method Status Protocol
            records.append(
                {
                    "interface": parts[0],
                    "ip_address": parts[1],
                    "ok": parts[2],
                    "method": parts[3],
                    "status": " ".join(parts[4:-1]),
                    "protocol": parts[-1],
                }
            )

        if not records:
            return None
        return {"count": len(records), "interfaces": records}

    @classmethod
    def _parse_display_ip_interface_brief(cls, output: str) -> dict[str, Any] | None:
        lines = cls._split_non_empty_lines(output)
        hdr_idx = -1
        for idx, ln in enumerate(lines):
            lo = ln.lower()
            if "interface" in lo and ("physical" in lo or "protocol" in lo):
                hdr_idx = idx
                break
        if hdr_idx < 0:
            return None

        records: list[dict[str, str]] = []
        for ln in lines[hdr_idx + 1 :]:
            if re.match(r"^-{3,}$", ln.replace(" ", "")):
                continue
            parts = ln.split()
            if len(parts) < 5:
                continue
            records.append(
                {
                    "interface": parts[0],
                    "ip_address": parts[1],
                    "physical": parts[2],
                    "protocol": parts[3],
                    "vpn": " ".join(parts[4:]),
                }
            )

        if not records:
            return None
        return {"count": len(records), "interfaces": records}

    @classmethod
    def _parse_version(cls, output: str) -> dict[str, Any] | None:
        text = output
        result: dict[str, Any] = {}

        m = re.search(r"(Cisco IOS.*Version\s+([^,\s]+))", text, re.IGNORECASE)
        if m:
            result["os_line"] = m.group(1).strip()
            result["version"] = m.group(2).strip()

        if "version" not in result:
            m2 = re.search(r"VRP.*Version\s+([^\s,]+)", text, re.IGNORECASE)
            if m2:
                result["version"] = m2.group(1).strip()

        m3 = re.search(r"[Pp]rocessor board ID\s+(\S+)", text)
        if m3:
            result["serial_number"] = m3.group(1)

        m4 = re.search(r"(?m)^(\S+)\s+uptime is\s+(.+)$", text)
        if m4:
            result["hostname"] = m4.group(1)
            result["uptime"] = m4.group(2).strip()

        m5 = re.search(r"cisco\s+(\S+)\s+\(", text, re.IGNORECASE)
        if m5:
            result["model"] = m5.group(1)

        if not result:
            return None
        return result

    @classmethod
    def _parse_routes(cls, output: str) -> dict[str, Any] | None:
        lines = cls._split_non_empty_lines(output)
        routes: list[dict[str, str]] = []

        for ln in lines:
            # Cisco: O 10.0.0.0/24 [110/2] via 1.1.1.1, 00:00:12, Gi0/0
            m = re.match(r"^\s*([A-Z\*]+)\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+.+\s+via\s+(\d+\.\d+\.\d+\.\d+)", ln)
            if m:
                routes.append({"protocol": m.group(1), "prefix": m.group(2), "next_hop": m.group(3)})
                continue

            # Huawei/H3C 常见: 10.0.0.0/24   Static 60 0 RD 1.1.1.1 GigabitEthernet...
            m2 = re.match(
                r"^\s*(\d+\.\d+\.\d+\.\d+/\d+)\s+([A-Za-z]+)\s+\d+\s+\d+\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)",
                ln,
            )
            if m2:
                routes.append(
                    {
                        "prefix": m2.group(1),
                        "protocol": m2.group(2),
                        "next_hop": m2.group(3),
                        "outgoing_interface": m2.group(4),
                    }
                )

        if not routes:
            return None
        return {"count": len(routes), "routes": routes}

    @classmethod
    def _parse_arp(cls, output: str) -> dict[str, Any] | None:
        lines = cls._split_non_empty_lines(output)
        entries: list[dict[str, str]] = []

        for ln in lines:
            # Cisco: Internet 10.1.1.1 0 aaaa.bbbb.cccc ARPA Vlan10
            m = re.match(
                r"^\s*Internet\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+|-)\s+([0-9a-fA-F\.\-:]+)\s+(\S+)\s+(\S+)",
                ln,
            )
            if m:
                entries.append(
                    {
                        "ip_address": m.group(1),
                        "age": m.group(2),
                        "mac_address": m.group(3),
                        "type": m.group(4),
                        "interface": m.group(5),
                    }
                )
                continue

            # Huawei/H3C: 10.1.1.1  aaaa-bbbb-cccc  VLAN10  GE1/0/1
            m2 = re.match(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\.\-:]+)\s+(\S+)\s+(\S+)", ln)
            if m2 and not ln.lower().startswith(("ip", "address", "total")):
                entries.append(
                    {
                        "ip_address": m2.group(1),
                        "mac_address": m2.group(2),
                        "vlan_or_type": m2.group(3),
                        "interface": m2.group(4),
                    }
                )

        if not entries:
            return None
        return {"count": len(entries), "entries": entries}
