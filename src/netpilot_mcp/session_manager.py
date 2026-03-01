"""会话管理器：管理多设备连接会话（Netmiko 实现）"""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from dataclasses import dataclass, field

from netmiko import SSHDetect

from .drivers.base import BaseDriver, CommandResult, DeviceMode
from .drivers.cisco_ios import CiscoIOSDriver
from .drivers.generic import GenericDriver
from .drivers.h3c_comware import H3CComwareDriver
from .drivers.huawei_vrp import HuaweiVRPDriver
from .drivers.ruijie_rgos import RuijieRGOSDriver
from .transport.base import BaseTransport
from .transport.netmiko_transport import HostKeyPolicy, NetmikoTransport
from .utils.output_parser import OutputParser
from .utils.structured_output import StructuredOutputParser

# 设备类型 → 驱动映射
DRIVER_MAP: dict[str, type[BaseDriver]] = {
    "cisco_ios": CiscoIOSDriver,
    "huawei_vrp": HuaweiVRPDriver,
    "h3c_comware": H3CComwareDriver,
    "ruijie_rgos": RuijieRGOSDriver,
    "generic": GenericDriver,
}

# 自动识别关键字 → 设备类型
AUTO_DETECT_KEYWORDS: list[tuple[str, str]] = [
    ("Cisco IOS", "cisco_ios"),
    ("IOS-XE", "cisco_ios"),
    ("Cisco Internetwork", "cisco_ios"),
    ("Huawei Versatile Routing", "huawei_vrp"),
    ("VRP", "huawei_vrp"),
    ("Comware", "h3c_comware"),
    ("H3C", "h3c_comware"),
    ("Ruijie", "ruijie_rgos"),
    ("RGOS", "ruijie_rgos"),
]

INTERNAL_TO_NETMIKO: dict[str, str] = {
    "cisco_ios": "cisco_ios",
    "huawei_vrp": "huawei",
    "h3c_comware": "hp_comware",
    "ruijie_rgos": "ruijie_os",
    "generic": "generic",
}


@dataclass
class Session:
    """单个设备连接会话"""

    session_id: str
    host: str
    port: int
    protocol: str
    device_type: str
    netmiko_device_type: str
    transport: BaseTransport
    driver: BaseDriver
    device_mode: str = ""
    hostname: str = ""
    connected_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionManager:
    """管理所有设备连接会话"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    async def create_session(
        self,
        host: str,
        port: int | None = None,
        protocol: str = "telnet",
        username: str = "",
        password: str = "",
        enable_password: str = "",
        device_type: str = "auto",
        timeout: int = 5000,
    ) -> dict:
        """创建新的设备连接会话"""
        protocol = protocol.lower().strip()
        if protocol not in {"ssh", "telnet"}:
            raise ValueError("protocol 仅支持 ssh 或 telnet")

        if port is None:
            port = 23 if protocol == "telnet" else 22

        if protocol == "telnet" and not self._telnet_enabled():
            raise PermissionError("Telnet 已禁用，请使用 SSH 或设置 NETPILOT_ALLOW_TELNET=true")

        host_key_policy = HostKeyPolicy(
            strict=self._strict_host_key_enabled(),
            known_hosts_file=os.environ.get("NETPILOT_KNOWN_HOSTS_FILE", "").strip(),
        )

        internal_device_type, netmiko_device_type = await self._resolve_device_types(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password,
            timeout=timeout,
            requested_device_type=device_type,
            host_key_policy=host_key_policy,
        )

        transport = NetmikoTransport(
            host=host,
            port=port,
            timeout=timeout,
            netmiko_device_type=netmiko_device_type,
            protocol=protocol,
            host_key_policy=host_key_policy,
        )

        initial_output = await transport.connect(username, password, enable_password)
        initial_output = OutputParser.remove_ansi_codes(initial_output)
        initial_output = OutputParser.remove_carriage_returns(initial_output)

        # Telnet auto 情况下，连接后基于提示符再做一次兜底识别
        if device_type == "auto" and protocol == "telnet":
            internal_device_type = self._auto_detect_device_type(initial_output)
            netmiko_device_type = self._internal_to_netmiko(internal_device_type, protocol)

        driver_cls = DRIVER_MAP.get(internal_device_type, GenericDriver)
        driver = driver_cls()

        # 先尝试进入特权模式，再禁用分页，提升后续命令稳定性
        if driver.get_enter_enable_command():
            try:
                await transport.enable()
            except Exception:
                pass

        disable_paging_cmd = driver.get_disable_paging_command()
        if disable_paging_cmd:
            try:
                await transport.execute_command(disable_paging_cmd, read_timeout_ms=5000)
            except Exception:
                pass

        prompt_output = await transport.find_prompt()
        prompt_output = OutputParser.remove_ansi_codes(prompt_output)
        prompt_output = OutputParser.remove_carriage_returns(prompt_output)

        detect_text = prompt_output if prompt_output.strip() else initial_output
        device_mode = driver.detect_mode(detect_text)
        hostname = driver.extract_hostname(detect_text)

        session_id = str(uuid.uuid4())[:8]
        session = Session(
            session_id=session_id,
            host=host,
            port=port,
            protocol=protocol,
            device_type=internal_device_type,
            netmiko_device_type=netmiko_device_type,
            transport=transport,
            driver=driver,
            device_mode=device_mode.value,
            hostname=hostname,
        )
        self._sessions[session_id] = session

        return {
            "session_id": session_id,
            "device_mode": device_mode.value,
            "device_type": internal_device_type,
            "netmiko_device_type": netmiko_device_type,
            "hostname": hostname,
            "protocol": protocol,
            "host": host,
            "port": port,
        }

    async def execute_command(
        self,
        session_id: str,
        command: str,
        wait_ms: int | None = None,
        expect_prompt: str = "",
    ) -> CommandResult:
        """在指定会话中执行命令"""
        session = self._get_session(session_id)
        driver = session.driver
        transport = session.transport

        if wait_ms is None:
            wait_ms = driver.get_long_running_timeout() if driver.is_long_running_command(command) else 5000

        async with session.lock:
            start_time = time.time()
            raw_output = await transport.execute_command(
                command=command,
                read_timeout_ms=wait_ms,
                # 仅在用户显式指定 expect_prompt 时传给 Netmiko；
                # 默认让 Netmiko 使用自身 prompt 识别，避免正则不匹配导致超时异常。
                expect_prompt=expect_prompt,
            )
            execution_time = int((time.time() - start_time) * 1000)

            clean_raw = OutputParser.remove_ansi_codes(raw_output)
            clean_raw = OutputParser.remove_carriage_returns(clean_raw)
            cleaned_output = driver.clean_output(clean_raw, command)
            structured = StructuredOutputParser.parse(command, cleaned_output, device_type=session.device_type)

            device_mode = driver.detect_mode(clean_raw)
            if device_mode == DeviceMode.UNKNOWN:
                try:
                    prompt_output = await transport.find_prompt()
                    device_mode = driver.detect_mode(prompt_output)
                except Exception:
                    pass
            session.device_mode = device_mode.value

        return CommandResult(
            success=True,
            output=cleaned_output,
            structured_output=structured.data,
            structured_status=structured.status,
            structured_parser=structured.parser,
            device_mode=session.device_mode,
            execution_time_ms=execution_time,
        )

    async def configure(
        self,
        session_id: str,
        commands: list[str],
        save_config: bool = False,
    ) -> dict:
        """进入配置模式执行批量命令"""
        session = self._get_session(session_id)
        driver = session.driver
        transport = session.transport
        results: list[dict] = []

        async with session.lock:
            # 逐条配置，保留每条命令结果，兼容原有 MCP 输出结构
            for idx, cmd in enumerate(commands):
                output = await transport.send_config_set(
                    [cmd],
                    read_timeout_ms=10000,
                    enter_config_mode=(idx == 0),
                    exit_config_mode=False,
                )
                clean_raw = OutputParser.remove_ansi_codes(output)
                clean_raw = OutputParser.remove_carriage_returns(clean_raw)
                cleaned = driver.clean_output(clean_raw, cmd)
                results.append({"command": cmd, "output": cleaned})

            exit_cmd = driver.get_exit_config_command()
            if exit_cmd:
                await transport.execute_command(exit_cmd, read_timeout_ms=5000)

            if save_config:
                save_cmd = driver.get_save_config_command()
                await transport.save_config(save_cmd)

            try:
                prompt = await transport.find_prompt()
                mode = driver.detect_mode(prompt)
            except Exception:
                mode = DeviceMode.PRIVILEGED
            session.device_mode = mode.value

        return {
            "results": results,
            "device_mode": session.device_mode,
            "config_saved": save_config,
        }

    async def disconnect_session(self, session_id: str) -> dict:
        """断开指定会话"""
        session = self._get_session(session_id)
        await session.transport.disconnect()
        del self._sessions[session_id]
        return {"session_id": session_id, "message": "已断开连接"}

    def list_sessions(self) -> list[dict]:
        """列出所有活跃会话"""
        return [
            {
                "session_id": s.session_id,
                "host": s.host,
                "port": s.port,
                "protocol": s.protocol,
                "device_type": s.device_type,
                "netmiko_device_type": s.netmiko_device_type,
                "hostname": s.hostname,
                "device_mode": s.device_mode,
                "connected_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.connected_at)),
            }
            for s in self._sessions.values()
        ]

    def _get_session(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise ValueError(f"会话 {session_id} 不存在。当前活跃会话: {list(self._sessions.keys()) or '无'}")
        return self._sessions[session_id]

    async def _resolve_device_types(
        self,
        host: str,
        port: int,
        protocol: str,
        username: str,
        password: str,
        timeout: int,
        requested_device_type: str,
        host_key_policy: HostKeyPolicy,
    ) -> tuple[str, str]:
        requested = requested_device_type.lower().strip()
        if requested and requested != "auto":
            internal = requested if requested in DRIVER_MAP else "generic"
            return internal, self._internal_to_netmiko(internal, protocol)

        # auto
        if protocol == "ssh":
            try:
                detected = await self._detect_by_ssh(
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                    host_key_policy=host_key_policy,
                )
                internal = self._netmiko_to_internal(detected)
                return internal, detected
            except Exception:
                pass

        return "generic", self._internal_to_netmiko("generic", protocol)

    async def _detect_by_ssh(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: int,
        host_key_policy: HostKeyPolicy,
    ) -> str:
        timeout_sec = max(timeout / 1000.0, 1.0)
        kwargs = {
            "device_type": "autodetect",
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "conn_timeout": timeout_sec,
            "banner_timeout": timeout_sec,
            "auth_timeout": timeout_sec,
        }
        if host_key_policy.strict:
            kwargs["ssh_strict"] = True
            kwargs["system_host_keys"] = True
            if host_key_policy.known_hosts_file:
                kwargs["alt_host_keys"] = True
                kwargs["alt_key_file"] = host_key_policy.known_hosts_file
        else:
            kwargs["ssh_strict"] = False
            kwargs["system_host_keys"] = False

        detector = await asyncio.to_thread(SSHDetect, **kwargs)
        detected = await asyncio.to_thread(detector.autodetect)
        if not detected:
            return "generic"
        return detected

    def _internal_to_netmiko(self, internal_device_type: str, protocol: str) -> str:
        base = INTERNAL_TO_NETMIKO.get(internal_device_type, "generic")
        return f"{base}_telnet" if protocol == "telnet" else base

    def _netmiko_to_internal(self, netmiko_device_type: str) -> str:
        normalized = netmiko_device_type.strip().lower()
        if normalized.endswith("_telnet"):
            normalized = normalized[: -len("_telnet")]

        if normalized.startswith("cisco_ios"):
            return "cisco_ios"
        if normalized.startswith("huawei"):
            return "huawei_vrp"
        if normalized.startswith("hp_comware"):
            return "h3c_comware"
        if normalized.startswith("ruijie_os"):
            return "ruijie_rgos"
        return "generic"

    def _auto_detect_device_type(self, output: str) -> str:
        for keyword, device_type in AUTO_DETECT_KEYWORDS:
            if keyword.lower() in output.lower():
                return device_type

        stripped = output.strip()
        if stripped:
            last_line = stripped.split("\n")[-1].strip()
            if re.search(r"<\S+>", last_line) or re.search(r"\[\S+\]", last_line):
                return "huawei_vrp"

        return "generic"

    @staticmethod
    def _strict_host_key_enabled() -> bool:
        value = os.environ.get("NETPILOT_SSH_STRICT_HOST_KEY", "true").strip().lower()
        return value in {"1", "true", "yes", "on"}

    @staticmethod
    def _telnet_enabled() -> bool:
        value = os.environ.get("NETPILOT_ALLOW_TELNET", "true").strip().lower()
        return value in {"1", "true", "yes", "on"}
