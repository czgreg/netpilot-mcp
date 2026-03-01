"""Netmiko 传输层实现（统一 SSH/Telnet）"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from .base import BaseTransport


@dataclass
class HostKeyPolicy:
    """SSH host key 校验策略"""

    strict: bool = True
    known_hosts_file: str = ""


class NetmikoTransport(BaseTransport):
    """基于 Netmiko 的统一传输实现"""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: int = 5000,
        netmiko_device_type: str = "generic",
        protocol: str = "ssh",
        host_key_policy: HostKeyPolicy | None = None,
    ):
        super().__init__(host, port, timeout)
        self.netmiko_device_type = netmiko_device_type
        self.protocol_name = protocol
        self.host_key_policy = host_key_policy or HostKeyPolicy()
        self._conn: BaseConnection | None = None

    async def connect(self, username: str = "", password: str = "", enable_password: str = "") -> str:
        """建立连接并返回初始提示符"""
        try:
            self._conn = await asyncio.to_thread(
                self._connect_sync,
                username,
                password,
                enable_password,
            )
        except NetmikoTimeoutException as e:
            raise ConnectionError(f"连接超时: {self.host}:{self.port} ({self.timeout}ms) - {e}") from e
        except NetmikoAuthenticationException as e:
            raise ConnectionError(f"认证失败: {self.host}:{self.port} - 用户名或密码错误") from e
        except Exception as e:
            raise ConnectionError(f"连接失败: {self.host}:{self.port} - {e}") from e

        self._connected = True
        return await self.find_prompt()

    def _connect_sync(self, username: str, password: str, enable_password: str) -> BaseConnection:
        timeout_sec = max(self.timeout / 1000.0, 1.0)
        connect_kwargs = {
            "device_type": self.netmiko_device_type,
            "host": self.host,
            "port": self.port,
            "username": username,
            "password": password,
            "secret": enable_password,
            "conn_timeout": timeout_sec,
            "banner_timeout": timeout_sec,
            "auth_timeout": timeout_sec,
            "fast_cli": False,
            "session_timeout": max(timeout_sec * 4, 30.0),
        }

        if self.protocol_name == "ssh":
            if self.host_key_policy.strict:
                connect_kwargs["ssh_strict"] = True
                connect_kwargs["system_host_keys"] = True
                if self.host_key_policy.known_hosts_file:
                    connect_kwargs["alt_host_keys"] = True
                    connect_kwargs["alt_key_file"] = self.host_key_policy.known_hosts_file
            else:
                connect_kwargs["ssh_strict"] = False
                connect_kwargs["system_host_keys"] = False

        return ConnectHandler(**connect_kwargs)

    async def send(self, data: str) -> None:
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")
        await asyncio.to_thread(self._conn.write_channel, data)

    async def read_until_prompt(self, prompt_pattern: str, timeout_ms: int = 2000) -> str:
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")
        read_timeout = max(timeout_ms / 1000.0, 1.0)
        return await asyncio.to_thread(
            self._conn.read_until_pattern,
            pattern=prompt_pattern,
            read_timeout=read_timeout,
        )

    async def read_available(self, timeout_ms: int = 500) -> str:
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")
        read_timeout = max(timeout_ms / 1000.0, 0.5)
        return await asyncio.to_thread(self._conn.read_channel_timing, read_timeout=read_timeout)

    async def execute_command(
        self,
        command: str,
        read_timeout_ms: int = 5000,
        expect_prompt: str = "",
    ) -> str:
        """执行 show/display 类命令"""
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")

        kwargs = {
            "read_timeout": max(read_timeout_ms / 1000.0, 1.0),
            "strip_prompt": False,
            "strip_command": False,
            "cmd_verify": False,
        }
        if expect_prompt:
            kwargs["expect_string"] = expect_prompt

        return await asyncio.to_thread(self._conn.send_command, command, **kwargs)

    async def send_config_set(
        self,
        commands: list[str],
        read_timeout_ms: int = 10000,
        enter_config_mode: bool = True,
        exit_config_mode: bool = True,
    ) -> str:
        """执行批量配置命令"""
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")

        kwargs = {
            "read_timeout": max(read_timeout_ms / 1000.0, 1.0),
            "enter_config_mode": enter_config_mode,
            "exit_config_mode": exit_config_mode,
            "strip_prompt": False,
            "strip_command": False,
            "cmd_verify": False,
        }
        return await asyncio.to_thread(self._conn.send_config_set, commands, **kwargs)

    async def save_config(self, cmd: str = "") -> str:
        """保存配置"""
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")

        if cmd:
            return await self.execute_command(cmd, read_timeout_ms=20000)

        if hasattr(self._conn, "save_config"):
            return await asyncio.to_thread(self._conn.save_config)

        return ""

    async def find_prompt(self) -> str:
        """读取当前提示符"""
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")
        return await asyncio.to_thread(self._conn.find_prompt)

    async def enable(self) -> str:
        """进入特权模式（若设备支持）"""
        if not self._connected or not self._conn:
            raise ConnectionError("设备未连接")
        return await asyncio.to_thread(self._conn.enable)

    async def disconnect(self) -> None:
        if self._conn:
            try:
                await asyncio.to_thread(self._conn.disconnect)
            except Exception:
                pass
        self._connected = False
        self._conn = None

    @property
    def protocol(self) -> str:
        return self.protocol_name
