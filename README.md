# NetPilot-MCP 🚀

**智能网络设备管理 MCP 库** — 让大模型通过自然语言管理你的网络设备

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 简介

NetPilot-MCP 是一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 的网络设备管理库，支持大语言模型（Claude、Cursor、Copilot 等）通过 **Telnet/SSH** 协议直接连接和管理网络设备。

### ✨ 特性

- **双协议支持** — 同时支持 Telnet 和 SSH
- **多厂商兼容** — Cisco IOS、华为 VRP、H3C Comware、锐捷 RGOS
- **智能识别** — 自动检测设备类型、提示符、操作模式
- **安全控制** — 命令三级分级（安全/敏感/危险）、危险命令拦截
- **审计日志** — 完整记录所有设备操作，自动脱敏密码
- **即装即用** — pip 安装，一行配置即可集成 AI 客户端

## 安装

```bash
git clone https://github.com/czgreg/netpilot-mcp.git
cd netpilot-mcp
pip install -e .
```

## 使用

### 启动 MCP Server

```bash
netpilot-mcp
```

### 配置 AI 客户端

在 MCP 客户端配置文件中添加（以 Claude Desktop 为例）：

```json
{
  "mcpServers": {
    "netpilot-mcp": {
      "command": "netpilot-mcp"
    }
  }
}
```

### 配置 Cursor

在 Cursor 的 MCP 设置中添加：

```json
{
  "mcpServers": {
    "netpilot-mcp": {
      "command": "netpilot-mcp"
    }
  }
}
```

### 环境变量（可选）

```bash
export NETPILOT_USERNAME=admin
export NETPILOT_PASSWORD=your_password
```

## MCP Tools

| Tool | 类别 | 说明 |
|------|------|------|
| `device_connect` | 连接管理 | 连接设备（Telnet/SSH） |
| `device_disconnect` | 连接管理 | 断开连接 |
| `device_list_sessions` | 连接管理 | 列出活跃会话 |
| `device_execute` | 命令执行 | 执行单条命令 |
| `device_configure` | 命令执行 | 批量配置命令 |
| `device_get_info` | 信息查询 | 获取设备信息 |
| `device_get_config` | 信息查询 | 获取设备配置 |
| `device_ping` | 网络诊断 | Ping 测试 |
| `device_traceroute` | 网络诊断 | 路由追踪 |

## 支持设备

| 厂商 | 类型标识 | 命令体系 |
|------|----------|----------|
| Cisco IOS/IOS-XE | `cisco_ios` | show 命令 |
| 华为 VRP | `huawei_vrp` | display 命令 |
| H3C Comware | `h3c_comware` | display 命令 |
| 锐捷 RGOS | `ruijie_rgos` | show 命令 |
| 通用设备 | `generic` | show 命令 |

## 使用示例

### 示例 1: 查看接口状态

```
用户：帮我看看 192.168.1.1 交换机的接口状态

AI 自动执行：
→ device_connect(host="192.168.1.1", protocol="ssh")
→ device_execute(command="show ip interface brief")
→ 分析输出并汇报
→ device_disconnect()
```

### 示例 2: 批量配置

```
用户：把核心交换机 GE0/0/1-4 改成 trunk 模式

AI 自动执行：
→ device_connect(host="10.0.0.1", device_type="huawei_vrp")
→ device_configure(commands=[...], save_config=true)
→ 验证配置
→ device_disconnect()
```

## 推荐 System Prompt

```text
你是网络设备管理助手，可以通过 netpilot-mcp 工具管理网络设备。

1. 使用 device_connect 连接设备，可选 telnet 或 ssh 协议
2. 对 ping、traceroute 等耗时命令，wait_ms 建议设置 10000-30000ms
3. 注意当前设备模式（用户/特权/配置），命令要匹配对应模式
4. 使用 device_list_sessions 复用已有连接，避免重复连接
5. 操作前先用 show/display 确认当前状态
6. 配置变更后用 save_config=true 保存
7. 操作结束后断开连接
```

## ⚠️ 安全提示

- Telnet 为明文传输，仅建议在**实验环境和内网**使用
- 生产环境请使用 **SSH** 协议
- 危险命令（reload、erase 等）会被自动拦截

## License

MIT License
