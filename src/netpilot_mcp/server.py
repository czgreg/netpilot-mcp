"""
NetPilot-MCP Server：主入口文件
使用 FastMCP 框架注册所有 MCP Tools
"""

import json
import os
from mcp.server.fastmcp import FastMCP

from .session_manager import SessionManager
from .security.command_guard import CommandGuard
from .security.audit_logger import AuditLogger


# 创建 MCP Server
mcp = FastMCP(
    "netpilot-mcp",
    instructions="NetPilot-MCP: 智能网络设备管理，支持 Telnet/SSH 连接 Cisco/华为/H3C/锐捷等网络设备",
)

# 全局实例
session_manager = SessionManager()
audit_logger = AuditLogger()

# 加载安全规则
_security_rules_path = os.environ.get(
    "NETPILOT_SECURITY_RULES",
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "security_rules.json"),
)
command_guard = CommandGuard.from_config_file(_security_rules_path)


# ============================================================
# 连接管理 Tools
# ============================================================


@mcp.tool()
async def device_connect(
    host: str,
    port: int | None = None,
    protocol: str = "telnet",
    username: str = "",
    password: str = "",
    enable_password: str = "",
    device_type: str = "auto",
    timeout: int = 5000,
) -> str:
    """
    连接到网络设备。

    建立 Telnet 或 SSH 连接，自动完成登录认证并识别设备类型。

    Args:
        host: 设备 IP 地址或主机名
        port: 端口号（Telnet 默认 23，SSH 默认 22）
        protocol: 连接协议，telnet 或 ssh
        username: 登录用户名
        password: 登录密码
        enable_password: Enable/特权模式密码
        device_type: 设备类型（cisco_ios/huawei_vrp/h3c_comware/ruijie_rgos/auto）
        timeout: 连接超时（毫秒）

    Returns:
        连接结果，包含 session_id 和设备信息
    """
    # 从环境变量获取凭证（如果未在参数中指定）
    if not username:
        username = os.environ.get("NETPILOT_USERNAME", "")
    if not password:
        password = os.environ.get("NETPILOT_PASSWORD", "")

    try:
        result = await session_manager.create_session(
            host=host,
            port=port,
            protocol=protocol,
            username=username,
            password=password,
            enable_password=enable_password,
            device_type=device_type,
            timeout=timeout,
        )

        audit_logger.log_connect(
            result["session_id"], host, result["port"], protocol, result["device_type"]
        )

        return json.dumps({
            "success": True,
            "session_id": result["session_id"],
            "device_mode": result["device_mode"],
            "device_type": result["device_type"],
            "hostname": result["hostname"],
            "protocol": result["protocol"],
            "message": f"已通过 {protocol.upper()} 连接到 {host}:{result['port']}",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": f"连接失败: {e}",
        }, ensure_ascii=False)


@mcp.tool()
async def device_disconnect(session_id: str) -> str:
    """
    断开指定的设备连接会话。

    Args:
        session_id: 会话 ID
    """
    try:
        # 获取 host 信息用于日志
        sessions = session_manager.list_sessions()
        host = next((s["host"] for s in sessions if s["session_id"] == session_id), "unknown")

        result = await session_manager.disconnect_session(session_id)
        audit_logger.log_disconnect(session_id, host)

        return json.dumps({
            "success": True,
            "message": result["message"],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


@mcp.tool()
async def device_list_sessions() -> str:
    """列出所有活跃的设备连接会话。"""
    sessions = session_manager.list_sessions()
    return json.dumps({
        "success": True,
        "sessions": sessions,
        "count": len(sessions),
    }, ensure_ascii=False)


# ============================================================
# 命令执行 Tools
# ============================================================


@mcp.tool()
async def device_execute(
    session_id: str,
    command: str,
    wait_ms: int | None = None,
    expect_prompt: str = "",
) -> str:
    """
    在指定设备上执行单条命令。

    会自动检测耗时命令（如 ping、traceroute）并增加等待时间。

    Args:
        session_id: 会话 ID
        command: 要执行的命令
        wait_ms: 最大等待时间（毫秒），ping/traceroute 等自动增加
        expect_prompt: 自定义期望提示符（正则表达式）
    """
    # 安全检查
    check = command_guard.check(command)
    if not check.allowed:
        sessions = session_manager.list_sessions()
        host = next((s["host"] for s in sessions if s["session_id"] == session_id), "unknown")
        audit_logger.log_security_block(session_id, host, command, check.message)
        return json.dumps({
            "success": False,
            "security_level": check.level.value,
            "message": check.message,
        }, ensure_ascii=False)

    try:
        result = await session_manager.execute_command(
            session_id=session_id,
            command=command,
            wait_ms=wait_ms,
            expect_prompt=expect_prompt,
        )

        # 审计日志
        sessions = session_manager.list_sessions()
        host = next((s["host"] for s in sessions if s["session_id"] == session_id), "unknown")
        audit_logger.log_execute(session_id, host, command, result.success)

        response = {
            "success": result.success,
            "output": result.output,
            "device_mode": result.device_mode,
            "execution_time_ms": result.execution_time_ms,
        }

        # 如果是敏感命令，附加安全提示
        if check.message:
            response["security_notice"] = check.message

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


@mcp.tool()
async def device_configure(
    session_id: str,
    commands: list[str],
    save_config: bool = False,
) -> str:
    """
    进入配置模式并执行批量配置命令。

    自动处理模式切换，可选保存配置到设备。

    Args:
        session_id: 会话 ID
        commands: 配置命令列表
        save_config: 是否在配置完成后保存到设备
    """
    # 对每条命令进行安全检查
    for cmd in commands:
        check = command_guard.check(cmd)
        if not check.allowed:
            return json.dumps({
                "success": False,
                "blocked_command": cmd,
                "message": check.message,
            }, ensure_ascii=False)

    try:
        result = await session_manager.configure(
            session_id=session_id,
            commands=commands,
            save_config=save_config,
        )

        # 审计日志
        sessions = session_manager.list_sessions()
        host = next((s["host"] for s in sessions if s["session_id"] == session_id), "unknown")
        audit_logger.log_configure(session_id, host, commands, save_config)

        return json.dumps({
            "success": True,
            "results": result["results"],
            "device_mode": result["device_mode"],
            "config_saved": result["config_saved"],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


# ============================================================
# 信息查询 Tools
# ============================================================


@mcp.tool()
async def device_get_info(
    session_id: str,
    info_type: str = "version",
) -> str:
    """
    获取设备信息。

    Args:
        session_id: 会话 ID
        info_type: 信息类型 - version(版本)/interfaces(接口)/routing(路由表)/arp(ARP表)/all(全部)
    """
    try:
        session = session_manager._get_session(session_id)
        command = session.driver.get_info_command(info_type)

        result = await session_manager.execute_command(
            session_id=session_id,
            command=command,
        )

        return json.dumps({
            "success": True,
            "info_type": info_type,
            "command": command,
            "output": result.output,
            "device_mode": result.device_mode,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


@mcp.tool()
async def device_get_config(
    session_id: str,
    config_type: str = "running",
    section: str = "",
) -> str:
    """
    获取设备配置。

    Args:
        session_id: 会话 ID
        config_type: 配置类型 - running(运行配置)/startup(启动配置)
        section: 配置段过滤（如 interface、router 等）
    """
    try:
        session = session_manager._get_session(session_id)
        command = session.driver.get_config_command(config_type, section)

        result = await session_manager.execute_command(
            session_id=session_id,
            command=command,
            wait_ms=10000,  # 配置输出可能较长
        )

        return json.dumps({
            "success": True,
            "config_type": config_type,
            "section": section or "全部",
            "command": command,
            "output": result.output,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


# ============================================================
# 网络诊断 Tools
# ============================================================


@mcp.tool()
async def device_ping(
    session_id: str,
    target: str,
    count: int = 5,
    source: str = "",
) -> str:
    """
    在设备上执行 Ping 测试。

    Args:
        session_id: 会话 ID
        target: 目标 IP 地址或主机名
        count: Ping 次数
        source: 源接口或 IP 地址
    """
    try:
        session = session_manager._get_session(session_id)
        command = session.driver.get_ping_command(target, count, source)

        result = await session_manager.execute_command(
            session_id=session_id,
            command=command,
            wait_ms=30000,  # Ping 需要较长等待
        )

        return json.dumps({
            "success": True,
            "target": target,
            "command": command,
            "output": result.output,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


@mcp.tool()
async def device_traceroute(
    session_id: str,
    target: str,
) -> str:
    """
    在设备上执行路由追踪。

    Args:
        session_id: 会话 ID
        target: 目标 IP 地址或主机名
    """
    try:
        session = session_manager._get_session(session_id)
        command = session.driver.get_traceroute_command(target)

        result = await session_manager.execute_command(
            session_id=session_id,
            command=command,
            wait_ms=60000,  # Traceroute 可能非常耗时
        )

        return json.dumps({
            "success": True,
            "target": target,
            "command": command,
            "output": result.output,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)


# ============================================================
# 入口函数
# ============================================================


def main():
    """MCP Server 入口"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
