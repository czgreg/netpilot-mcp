"""Telnet 传输层实现"""

import asyncio
import re
import telnetlib3

from .base import BaseTransport


class TelnetTransport(BaseTransport):
    """基于 telnetlib3 的异步 Telnet 传输实现"""

    def __init__(self, host: str, port: int = 23, timeout: int = 5000):
        super().__init__(host, port, timeout)
        self._reader: telnetlib3.TelnetReader | None = None
        self._writer: telnetlib3.TelnetWriter | None = None

    async def connect(self, username: str = "", password: str = "", enable_password: str = "") -> str:
        """建立 Telnet 连接并完成登录认证"""
        timeout_sec = self.timeout / 1000.0

        try:
            self._reader, self._writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, self.port),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(f"Telnet 连接超时: {self.host}:{self.port} ({self.timeout}ms)")
        except Exception as e:
            raise ConnectionError(f"Telnet 连接失败: {self.host}:{self.port} - {e}")

        self._connected = True

        # 等待初始输出并处理登录
        output = await self._handle_login(username, password)
        return output

    async def _handle_login(self, username: str, password: str) -> str:
        """处理设备的登录认证流程"""
        collected_output = ""
        timeout_sec = self.timeout / 1000.0
        password_sent = False
        empty_rounds = 0  # 连续空数据轮次

        try:
            # 读取初始输出，寻找用户名/密码提示或设备提示符
            for _ in range(15):  # 最多尝试 15 轮交互
                chunk = await self._read_with_timeout(min(timeout_sec, 3.0))
                if not chunk:
                    empty_rounds += 1
                    # 连续 2 轮空数据：
                    # 如果有密码未发送，先尝试发送密码（华为静默密码场景）
                    if empty_rounds >= 2 and password and not password_sent:
                        self._writer.write(password + "\r\n")
                        password_sent = True
                        collected_output = ""
                        empty_rounds = 0
                        continue
                    # 如果已有有效输出且连续空数据，可能已到提示符
                    if empty_rounds >= 2:
                        clean_check = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", collected_output)
                        clean_check = re.sub(r"\x1b\][^\x07]*\x07?", "", clean_check)
                        if clean_check.strip():
                            break
                    continue

                empty_rounds = 0  # 有数据时重置
                collected_output += chunk

                # 去掉全部 ANSI 转义后检查（包括 OSC 标题序列）
                clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", collected_output)
                clean = re.sub(r"\x1b\][^\x07]*\x07?", "", clean)  # OSC 序列
                lower_output = clean.lower().strip()

                # 如果清洗后为空（只有 ANSI 控制字符），继续等待
                if not lower_output:
                    continue

                # 检测用户名提示
                if re.search(r"(username|login|用户名)\s*[:：]\s*$", lower_output):
                    if username:
                        self._writer.write(username + "\r\n")
                        collected_output = ""
                        continue

                # 检测密码提示
                if re.search(r"password\s*[:：]\s*$", lower_output) or \
                   re.search(r"密码\s*[:：]\s*$", lower_output):
                    if password and not password_sent:
                        self._writer.write(password + "\r\n")
                        password_sent = True
                        collected_output = ""
                        continue
                    elif password_sent:
                        break  # 密码错误
                    else:
                        self._writer.write("\r\n")
                        collected_output = ""
                        continue

                # 检测是否已经到达设备提示符（登录完成）
                if self._looks_like_prompt(clean):
                    break

        except asyncio.TimeoutError:
            pass

        return collected_output

    async def send(self, data: str) -> None:
        """发送数据到设备"""
        if not self._connected or not self._writer:
            raise ConnectionError("Telnet 未连接")
        self._writer.write(data)

    async def read_until_prompt(self, prompt_pattern: str, timeout_ms: int = 2000) -> str:
        """读取数据直到匹配提示符正则或超时"""
        if not self._connected or not self._reader:
            raise ConnectionError("Telnet 未连接")

        timeout_sec = timeout_ms / 1000.0
        collected = ""
        pattern = re.compile(prompt_pattern)
        deadline = asyncio.get_event_loop().time() + timeout_sec

        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            chunk = await self._read_with_timeout(min(remaining, 0.5))
            if chunk:
                collected += chunk
                # 检查是否匹配提示符
                if pattern.search(collected):
                    break

        return collected

    async def read_available(self, timeout_ms: int = 500) -> str:
        """读取当前可用数据"""
        if not self._connected or not self._reader:
            raise ConnectionError("Telnet 未连接")
        return await self._read_with_timeout(timeout_ms / 1000.0)

    async def _read_with_timeout(self, timeout_sec: float) -> str:
        """带超时的读取数据"""
        try:
            data = await asyncio.wait_for(
                self._reader.read(4096),
                timeout=timeout_sec,
            )
            return data if data else ""
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

    async def disconnect(self) -> None:
        """断开 Telnet 连接"""
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
        self._connected = False
        self._reader = None
        self._writer = None

    @staticmethod
    def _looks_like_prompt(text: str) -> bool:
        """简单判断文本末尾是否看起来像设备提示符"""
        stripped = text.strip()
        if not stripped:
            return False
        last_line = stripped.split("\n")[-1].strip()
        # 常见提示符模式: "xxx>" "xxx#" "<xxx>" "[xxx]"
        return bool(re.search(r"[>#\]]\s*$", last_line))
