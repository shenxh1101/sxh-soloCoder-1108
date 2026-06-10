# SSH Recorder

一个基于Python的命令行SSH会话录制与回放工具。

## 功能特性

- SSH会话录制（支持参数或配置文件连接）
- 实时记录所有输入输出（含转义序列和颜色）
- 带时间戳的日志文件
- 精简版日志生成（移除退格符和控制字符）
- 会话回放（支持原速和可调速播放）
- 回放书签标记功能
- HTML导出（模拟终端样式）
- 日志内容搜索
- 并发会话记录
- 自动按日期切割日志

## 安装

```bash
pip install -r requirements.txt
pip install -e .
```

## 快速开始

### 录制会话

```bash
# 通过参数直接连接
ssh-recorder record --host example.com --user admin --port 22

# 通过配置文件
ssh-recorder record --config servers.yaml --name prod-server
```

### 回放会话

```bash
ssh-recorder play logs/session-2024-01-01_12-00-00.log

# 2倍速播放
ssh-recorder play logs/session.log --speed 2.0

# 慢速回放
ssh-recorder play logs/session.log --speed 0.5
```

### 生成精简日志

```bash
ssh-recorder clean logs/session.log -o logs/session-clean.log
```

### 导出HTML

```bash
ssh-recorder export logs/session.log -o session.html
```

### 搜索日志

```bash
ssh-recorder search logs/ --query "ls -la"
```

## 配置文件示例 (servers.yaml)

```yaml
servers:
  prod-server:
    host: prod.example.com
    port: 22
    user: admin
    password: optional
    key_file: ~/.ssh/id_rsa
  dev-server:
    host: dev.example.com
    port: 22
    user: developer
```
