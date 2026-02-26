"""会话管理器：管理多设备的连接会话"""

import uuid
import time
import re
from dataclasses import dataclass, field

from .utils.output_parser import OutputParser

from .transport.base import BaseTransport
from .transport.telnet_transport import TelnetTransport
from .transport.ssh_transport import SSHTransport
from .drivers.base import BaseDriver, DeviceMode, CommandResult, DeviceInfo
from .drivers.cisco_ios import CiscoIOSDriver
from .drivers.huawei_vrp import HuaweiVRPDriver
from .drivers.h3c_comware import H3CComwareDriver
from .drivers.ruijie_rgos import RuijieRGOSDriver
from .drivers.generic import GenericDriver


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


@dataclass
class Session:
    """单个设备连接会话"""
    session_id: str
    host: str
    port: int
    protocol: str
    device_type: str
    transport: BaseTransport
    driver: BaseDriver
    device_mode: str = ""
    hostname: str = ""
    connected_at: float = field(default_factory=time.time)


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
        """
        创建新的设备连接会话。

        Returns:
            包含 session_id、device_mode、device_info 的字典
        """
        # 确定端口号
        if port is None:
            port = 23 if protocol == "telnet" else 22

        # 创建传输层
        if protocol == "ssh":
            transport = SSHTransport(host, port, timeout)
        else:
            transport = TelnetTransport(host, port, timeout)

        # 建立连接
        initial_output = await transport.connect(username, password, enable_password)

        # 清洗 ANSI 控制字符
        initial_output = OutputParser.remove_ansi_codes(initial_output)
        initial_output = OutputParser.remove_carriage_returns(initial_output)

        # 确定设备驱动
        if device_type == "auto":
            device_type = self._auto_detect_device_type(initial_output)

        driver_cls = DRIVER_MAP.get(device_type, GenericDriver)
        driver = driver_cls()

        # 发送空行获取干净的提示符
        await transport.send("\r\n")
        prompt_output = await transport.read_until_prompt(
            driver.combined_prompt_pattern, timeout_ms=3000
        )
        prompt_output = OutputParser.remove_ansi_codes(prompt_output)
        prompt_output = OutputParser.remove_carriage_returns(prompt_output)

        # 检测当前设备模式（用清洗后的提示符输出）
        detect_text = prompt_output if prompt_output.strip() else initial_output
        device_mode = driver.detect_mode(detect_text)
        hostname = driver.extract_hostname(detect_text)

        # 如果设备处于配置模式（华为/H3C 初始可能进入 console 配置视图），先退回
        if device_mode in (DeviceMode.CONFIG, DeviceMode.CONFIG_IF, DeviceMode.CONFIG_SUB):
            # 华为/H3C 用 return 退到用户视图，Cisco/锐捷用 end
            exit_cmds = ["return", "return", "quit"]
            for exit_cmd in exit_cmds:
                await transport.send(exit_cmd + "\r\n")
                exit_output = await transport.read_until_prompt(
                    driver.combined_prompt_pattern, timeout_ms=3000
                )
                exit_output = OutputParser.remove_ansi_codes(exit_output)
                exit_output = OutputParser.remove_carriage_returns(exit_output)
                device_mode = driver.detect_mode(exit_output)
                if device_mode in (DeviceMode.USER, DeviceMode.PRIVILEGED):
                    hostname = driver.extract_hostname(exit_output)
                    break

        # 禁用分页
        disable_paging_cmd = driver.get_disable_paging_command()
        if disable_paging_cmd:
            await transport.send(disable_paging_cmd + "\r\n")
            await transport.read_until_prompt(
                driver.combined_prompt_pattern, timeout_ms=3000
            )

        # 如果在用户模式，且有 enable 命令，尝试进入特权模式
        if device_mode == DeviceMode.USER and driver.get_enter_enable_command():
            await transport.send(driver.get_enter_enable_command() + "\r\n")
            enable_output = await transport.read_until_prompt(
                driver.combined_prompt_pattern + r"|[Pp]assword", timeout_ms=3000
            )
            # 如果需要 enable 密码
            if re.search(r"[Pp]assword", enable_output):
                if enable_password:
                    await transport.send(enable_password + "\r\n")
                    enable_output = await transport.read_until_prompt(
                        driver.combined_prompt_pattern, timeout_ms=3000
                    )
            device_mode = driver.detect_mode(enable_output)

        # 生成会话 ID
        session_id = str(uuid.uuid4())[:8]

        # 保存会话
        session = Session(
            session_id=session_id,
            host=host,
            port=port,
            protocol=protocol,
            device_type=device_type,
            transport=transport,
            driver=driver,
            device_mode=device_mode.value,
            hostname=hostname,
        )
        self._sessions[session_id] = session

        return {
            "session_id": session_id,
            "device_mode": device_mode.value,
            "device_type": device_type,
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

        # 计算超时
        if wait_ms is None:
            if driver.is_long_running_command(command):
                wait_ms = driver.get_long_running_timeout()
            else:
                wait_ms = 5000  # 默认 5 秒，避免 show version 等命令超时

        # 确定提示符模式
        prompt = expect_prompt if expect_prompt else driver.combined_prompt_pattern

        # 清空缓冲区残留数据，防止上一条命令的输出串流
        try:
            await transport.read_available(timeout_ms=200)
        except Exception:
            pass

        # 发送命令
        start_time = time.time()
        await transport.send(command + "\r\n")

        # 读取输出
        raw_output = await transport.read_until_prompt(prompt, timeout_ms=wait_ms)

        execution_time = int((time.time() - start_time) * 1000)

        # 清洗 ANSI 控制字符
        clean_raw = OutputParser.remove_ansi_codes(raw_output)
        clean_raw = OutputParser.remove_carriage_returns(clean_raw)

        # 清洗输出
        cleaned_output = driver.clean_output(clean_raw, command)

        # 检测当前模式
        device_mode = driver.detect_mode(clean_raw)
        session.device_mode = device_mode.value

        return CommandResult(
            success=True,
            output=cleaned_output,
            device_mode=device_mode.value,
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
        prompt = driver.combined_prompt_pattern

        results: list[dict] = []

        # 进入配置模式
        config_cmd = driver.get_enter_config_command()
        if config_cmd:
            await transport.send(config_cmd + "\r\n")
            await transport.read_until_prompt(prompt, timeout_ms=3000)

        # 逐条执行配置命令
        for cmd in commands:
            await transport.send(cmd + "\r\n")
            output = await transport.read_until_prompt(prompt, timeout_ms=3000)
            cleaned = driver.clean_output(output, cmd)
            results.append({"command": cmd, "output": cleaned})

        # 退出配置模式
        exit_cmd = driver.get_exit_config_command()
        if exit_cmd:
            await transport.send(exit_cmd + "\r\n")
            await transport.read_until_prompt(prompt, timeout_ms=3000)

        # 保存配置
        if save_config:
            save_cmd = driver.get_save_config_command()
            await transport.send(save_cmd + "\r\n")
            save_output = await transport.read_until_prompt(
                prompt + r"|confirm|Y/N|\[Y\]",
                timeout_ms=10000,
            )
            # 处理确认提示
            if re.search(r"confirm|Y/N|\[Y\]", save_output, re.IGNORECASE):
                await transport.send("y\r\n")
                await transport.read_until_prompt(prompt, timeout_ms=10000)

        # 更新当前模式
        mode_output = await transport.read_available(timeout_ms=500)
        all_output = mode_output
        device_mode = driver.detect_mode(all_output) if all_output else DeviceMode.PRIVILEGED
        session.device_mode = device_mode.value

        return {
            "results": results,
            "device_mode": session.device_mode,
            "config_saved": save_config,
        }

    async def disconnect_session(self, session_id: str) -> dict:
        """断开指定的会话"""
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
                "hostname": s.hostname,
                "device_mode": s.device_mode,
                "connected_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(s.connected_at)
                ),
            }
            for s in self._sessions.values()
        ]

    def _get_session(self, session_id: str) -> Session:
        """获取会话，不存在则抛异常"""
        if session_id not in self._sessions:
            raise ValueError(
                f"会话 {session_id} 不存在。"
                f"当前活跃会话: {list(self._sessions.keys()) or '无'}"
            )
        return self._sessions[session_id]

    def _auto_detect_device_type(self, output: str) -> str:
        """根据初始输出自动识别设备类型"""
        for keyword, device_type in AUTO_DETECT_KEYWORDS:
            if keyword.lower() in output.lower():
                return device_type

        # 通过提示符格式推测
        stripped = output.strip()
        if stripped:
            last_line = stripped.split("\n")[-1].strip()
            if re.search(r"<\S+>", last_line):
                # <hostname> 风格 → 华为/H3C
                return "huawei_vrp"
            elif re.search(r"\[\S+\]", last_line):
                return "huawei_vrp"

        return "generic"
