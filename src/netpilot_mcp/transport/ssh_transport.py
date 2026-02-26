"""SSH 传输层实现"""

import asyncio
import re

import asyncssh

from .base import BaseTransport


class SSHTransport(BaseTransport):
    """基于 asyncssh 的异步 SSH 传输实现"""

    def __init__(self, host: str, port: int = 22, timeout: int = 5000):
        super().__init__(host, port, timeout)
        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None
        self._buffer: str = ""

    async def connect(self, username: str = "", password: str = "", enable_password: str = "") -> str:
        """建立 SSH 连接"""
        timeout_sec = self.timeout / 1000.0

        connect_kwargs: dict = {
            "host": self.host,
            "port": self.port,
            "known_hosts": None,  # 禁用 host key 检查（实验/内网环境）
        }

        if username:
            connect_kwargs["username"] = username
        if password:
            connect_kwargs["password"] = password

        try:
            self._conn = await asyncio.wait_for(
                asyncssh.connect(**connect_kwargs),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(f"SSH 连接超时: {self.host}:{self.port} ({self.timeout}ms)")
        except asyncssh.PermissionDenied:
            raise ConnectionError(f"SSH 认证失败: {self.host}:{self.port} - 用户名或密码错误")
        except Exception as e:
            raise ConnectionError(f"SSH 连接失败: {self.host}:{self.port} - {e}")

        # 请求交互式 shell
        try:
            self._process = await self._conn.create_process(
                term_type="xterm",
                term_size=(200, 50),
            )
        except Exception as e:
            if self._conn:
                self._conn.close()
            raise ConnectionError(f"SSH Shell 创建失败: {e}")

        self._connected = True

        # 读取初始设备输出（提示符等）
        output = await self.read_available(timeout_ms=self.timeout)
        return output

    async def send(self, data: str) -> None:
        """发送数据到设备"""
        if not self._connected or not self._process:
            raise ConnectionError("SSH 未连接")
        self._process.stdin.write(data)

    async def read_until_prompt(self, prompt_pattern: str, timeout_ms: int = 2000) -> str:
        """读取数据直到匹配提示符或超时"""
        if not self._connected or not self._process:
            raise ConnectionError("SSH 未连接")

        timeout_sec = timeout_ms / 1000.0
        collected = ""
        pattern = re.compile(prompt_pattern)
        deadline = asyncio.get_event_loop().time() + timeout_sec

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            chunk = await self._read_chunk(min(remaining, 0.5))
            if chunk:
                collected += chunk
                if pattern.search(collected):
                    break

        return collected

    async def read_available(self, timeout_ms: int = 500) -> str:
        """读取当前可用数据"""
        if not self._connected or not self._process:
            raise ConnectionError("SSH 未连接")
        return await self._read_chunk(timeout_ms / 1000.0)

    async def _read_chunk(self, timeout_sec: float) -> str:
        """带超时的读取数据块"""
        try:
            data = await asyncio.wait_for(
                self._process.stdout.read(4096),
                timeout=timeout_sec,
            )
            return data if data else ""
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

    async def disconnect(self) -> None:
        """断开 SSH 连接"""
        if self._process:
            try:
                self._process.close()
            except Exception:
                pass
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._connected = False
        self._process = None
        self._conn = None
