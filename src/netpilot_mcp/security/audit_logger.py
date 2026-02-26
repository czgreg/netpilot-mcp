"""审计日志：记录所有设备操作"""

import logging
import time
import os


class AuditLogger:
    """操作审计日志记录器"""

    def __init__(self, log_dir: str | None = None):
        self.log_dir = log_dir or os.path.expanduser("~/.netpilot-mcp/logs")
        os.makedirs(self.log_dir, exist_ok=True)

        # 配置日志
        self._logger = logging.getLogger("netpilot.audit")
        self._logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if not self._logger.handlers:
            log_file = os.path.join(
                self.log_dir,
                f"audit_{time.strftime('%Y%m%d')}.log",
            )
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(
                logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
            self._logger.addHandler(fh)

    def log_connect(self, session_id: str, host: str, port: int, protocol: str, device_type: str):
        """记录连接事件"""
        self._logger.info(
            f"CONNECT | session={session_id} | host={host}:{port} | protocol={protocol} | type={device_type}"
        )

    def log_execute(self, session_id: str, host: str, command: str, success: bool):
        """记录命令执行事件（自动脱敏密码）"""
        safe_cmd = self._sanitize(command)
        status = "SUCCESS" if success else "FAILED"
        self._logger.info(
            f"EXECUTE | session={session_id} | host={host} | command={safe_cmd} | {status}"
        )

    def log_configure(self, session_id: str, host: str, commands: list[str], saved: bool):
        """记录配置变更事件"""
        safe_cmds = [self._sanitize(c) for c in commands]
        self._logger.info(
            f"CONFIGURE | session={session_id} | host={host} | commands={safe_cmds} | saved={saved}"
        )

    def log_disconnect(self, session_id: str, host: str):
        """记录断开事件"""
        self._logger.info(f"DISCONNECT | session={session_id} | host={host}")

    def log_security_block(self, session_id: str, host: str, command: str, reason: str):
        """记录安全拦截事件"""
        safe_cmd = self._sanitize(command)
        self._logger.warning(
            f"BLOCKED | session={session_id} | host={host} | command={safe_cmd} | reason={reason}"
        )

    @staticmethod
    def _sanitize(text: str) -> str:
        """脱敏处理：隐藏密码等敏感信息"""
        import re
        # 替换 password 后面的内容
        text = re.sub(
            r"(password|secret|key)\s+\S+",
            r"\1 ****",
            text,
            flags=re.IGNORECASE,
        )
        return text
