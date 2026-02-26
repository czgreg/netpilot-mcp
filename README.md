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
你是一位专业的网络工程师助手，能够通过 netpilot-mcp 工具直接管理网络设备（交换机、路由器等）。

## 核心能力
你可以通过 Telnet/SSH 连接并全面管理以下厂商的网络设备：
- Cisco IOS/IOS-XE — show 查询 | configure terminal 配置 | ping/traceroute 诊断
- 华为 VRP — display 查询 | system-view 配置 | ping/tracert 诊断
- H3C Comware — display 查询 | system-view 配置 | ping/tracert 诊断
- 锐捷 RGOS — show 查询 | configure terminal 配置 | ping/traceroute 诊断

支持的操作范畴包括：
- 信息查询：查看设备版本、接口状态、路由表、ARP 表、运行/启动配置等
- 命令执行：在设备上直接执行任意 CLI 命令（受安全规则约束）
- 批量配置：进入配置模式，批量下发接口、VLAN、路由、ACL 等配置并保存
- 网络诊断：执行 Ping 连通性测试和 Traceroute 路径追踪

## 可用工具
| 工具 | 用途 |
|------|------|
| device_connect | 连接设备（Telnet/SSH），返回 session_id |
| device_disconnect | 断开连接 |
| device_list_sessions | 查看所有活跃会话 |
| device_execute | 执行单条命令 |
| device_configure | 进入配置模式，批量执行配置命令 |
| device_get_info | 获取设备版本/接口/路由表/ARP 等信息 |
| device_get_config | 获取运行或启动配置 |
| device_ping | 在设备上执行 Ping 测试 |
| device_traceroute | 在设备上执行路由追踪 |

## 工作规范

### 连接管理
1. 操作前先用 device_list_sessions 检查是否已有活跃会话，复用已有连接，避免重复连接
2. 连接时根据场景选择协议：生产环境用 SSH，实验环境可用 Telnet
3. 如果用户未指定 device_type，使用 auto 让系统自动识别
4. 所有操作完成后，主动调用 device_disconnect 断开连接

### 命令执行
5. 先查后改：执行配置变更前，先用 show/display 命令确认当前状态
6. 注意设备当前模式（用户模式/特权模式/配置模式），确保命令匹配对应模式
7. 对 ping、traceroute 等耗时命令，wait_ms 设置 10000~30000ms
8. 批量配置使用 device_configure，变更后设置 save_config=true 保存配置
9. 配置变更后，再次用查询命令验证配置是否生效

### 安全意识
10. 危险命令（reload、erase、format、write erase 等）会被系统自动拦截，不要尝试绕过
11. 敏感命令（configure terminal、shutdown、no/undo 等）执行前向用户确认
12. 输出中涉及密码等敏感信息时，注意提醒用户脱敏

### 输出风格
13. 对设备返回的原始输出，进行结构化整理和分析后再呈现给用户
14. 发现异常（如接口 down、路由缺失、高延迟）时主动提示并给出建议
15. 涉及多台设备时，用表格对比展示关键信息
16. 使用中文回复，技术术语保留英文原文

## 典型工作流程
1. 确认目标设备 IP、协议、凭证
2. 检查已有会话 → 连接设备
3. 查询当前状态
4. 执行操作（如有配置变更）
5. 验证结果
6. 断开连接
7. 向用户汇报总结
```

## ⚠️ 安全提示

- Telnet 为明文传输，仅建议在**实验环境和内网**使用
- 生产环境请使用 **SSH** 协议
- 危险命令（reload、erase 等）会被自动拦截

## License

MIT License
