"""传输层抽象基类：定义 Telnet/SSH 连接的统一接口"""

from abc import ABC, abstractmethod


class BaseTransport(ABC):
    """网络传输层抽象基类，Telnet 和 SSH 均实现此接口"""

    def __init__(self, host: str, port: int, timeout: int = 5000):
        self.host = host
        self.port = port
        self.timeout = timeout  # 毫秒
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self, username: str = "", password: str = "", enable_password: str = "") -> str:
        """
        建立连接并完成认证。

        Args:
            username: 登录用户名
            password: 登录密码
            enable_password: Enable 密码（部分设备需要）

        Returns:
            连接后接收到的初始输出（含提示符）
        """
        pass

    @abstractmethod
    async def send(self, data: str) -> None:
        """
        发送数据到设备。

        Args:
            data: 要发送的字符串数据
        """
        pass

    @abstractmethod
    async def read_until_prompt(self, prompt_pattern: str, timeout_ms: int = 2000) -> str:
        """
        读取数据直到匹配提示符或超时。

        Args:
            prompt_pattern: 提示符正则表达式
            timeout_ms: 超时时间（毫秒）

        Returns:
            读取到的全部数据
        """
        pass

    @abstractmethod
    async def read_available(self, timeout_ms: int = 500) -> str:
        """
        读取当前可用的数据。

        Args:
            timeout_ms: 等待超时（毫秒）

        Returns:
            当前可用的数据
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass

    async def execute_command(
        self,
        command: str,
        read_timeout_ms: int = 5000,
        expect_prompt: str = "",
    ) -> str:
        """执行单条命令。默认由子类按需实现。"""
        raise NotImplementedError

    async def send_config_set(
        self,
        commands: list[str],
        read_timeout_ms: int = 10000,
        enter_config_mode: bool = True,
        exit_config_mode: bool = True,
    ) -> str:
        """执行配置命令集合。默认由子类按需实现。"""
        raise NotImplementedError

    async def save_config(self, cmd: str = "") -> str:
        """保存配置。默认由子类按需实现。"""
        raise NotImplementedError

    async def find_prompt(self) -> str:
        """获取当前设备提示符。默认由子类按需实现。"""
        raise NotImplementedError

    @property
    def protocol(self) -> str:
        """返回协议名称"""
        return self.__class__.__name__.replace("Transport", "").lower()
