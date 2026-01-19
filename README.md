# Xray SOCKS5 转 Shadowsocks 转换器

## 简介

这是一个轻量级、高性能的 SOCKS5 到 Shadowsocks 转换器，完全不依赖 Docker，内存占用极低，支持二维码、有效期管理和智能监控。

## ✨ 特性

- ✅ **零依赖** - 自动下载 Xray，无需 Docker
- ✅ **超轻量** - 内存占用仅 10-20MB
- ✅ **即开即用** - 一个脚本搞定一切
- ✅ **二维码支持** - 自动生成连接二维码
- ✅ **有效期管理** - 支持设置服务有效期
- ✅ **智能监控** - 自动故障检测和恢复
- ✅ **Web管理** - 现代化Web界面
- ✅ **统一工具** - 集成诊断、监控、测试功能
- ✅ **完全独立** - 所有文件在脚本目录

## 快速开始

### 方法1：一键安装（推荐）

```bash
# 下载并运行安装脚本
chmod +x install_native.sh
./install_native.sh
```

### 方法2：直接使用

```bash
# 直接运行主脚本
chmod +x xray_converter_simple.sh
./xray_converter_simple.sh
```

## 使用说明

### 1. 添加服务

运行脚本后选择 "1. 添加服务"，然后：

1. **输入节点名称**
   - 用于标识此 SOCKS5 代理的名称
   - 例如：`美国节点1`、`香港VPS`、`公司代理`

2. **输入 SOCKS5 代理信息**
   - 格式1：`IP:端口` （无认证）
   - 格式2：`IP:端口:用户名:密码` （有认证）
   - 示例：`149.119.147.4:44496:user:pass`

3. **选择有效期**
   - 永久有效
   - 7天、30天、90天
   - 自定义天数

4. **获取连接信息**
   - 自动生成 SS 端口和密码
   - 显示连接信息和二维码
   - 提供 SS 连接链接

### 2. 管理服务

- **列出服务** - 查看所有服务状态、节点名称和有效期
- **查看详情** - 显示完整连接信息和二维码
- **删除服务** - 安全删除指定服务
- **删除所有服务** - 一键清空所有服务（三重确认保护）
- **重启服务** - 批量重启所有服务

### 3. 备份恢复

- **备份配置** - 创建配置备份文件
- **恢复配置** - 从备份文件恢复配置
- **管理备份** - 查看、删除和清理备份文件

#### 备份功能特点：
- 自动时间戳命名
- 压缩存储节省空间
- 支持多备份文件管理
- 恢复前自动备份当前配置
- 智能清理旧备份文件

## 📁 目录结构

```
xray_converter_simple.sh    # 主转换器脚本
xray_diagnostics.sh         # 统一诊断工具
xray_monitor.sh             # 智能监控系统
ss_link_utils.py            # SS链接工具集
install_native.sh           # 原生安装脚本
deploy.sh                   # 一键部署脚本
xray                        # Xray 二进制文件（自动下载）
web_prototype/              # Web管理界面
├── app.py                 # Flask应用主文件
├── system_monitor.py      # 系统监控模块
├── api_extensions.py      # API扩展
└── templates/            # 网页模板
data/                       # 数据目录
├── services/               # 服务配置
│   ├── 12345/             # 端口号目录
│   │   ├── config.json    # Xray 配置
│   │   ├── info           # 服务信息（含节点名称）
│   │   ├── xray.pid       # 进程 ID
│   │   └── xray.log       # 运行日志
│   └── ...
├── xray_backup_*.tar.gz   # 自动备份文件
└── monitor.log            # 监控日志
```

## 连接客户端

### 连接信息示例

```
节点名称: 美国节点1
服务器地址: 1.2.3.4
端口: 12345
密码: abcd1234efgh
加密方式: aes-256-gcm
有效期至: 2024-02-15 10:30:00
```

### 支持的客户端

- **Windows**: Shadowsocks-Windows, v2rayN
- **macOS**: ShadowsocksX-NG, ClashX
- **iOS**: Shadowrocket, Quantumult X
- **Android**: Shadowsocks Android, v2rayNG

## 🛠️ 工具集

### 诊断工具
```bash
# 完整系统诊断
./xray_diagnostics.sh all

# 单独诊断
./xray_diagnostics.sh system    # 系统诊断
./xray_diagnostics.sh xray      # Xray诊断
./xray_diagnostics.sh service 端口号  # 单个服务诊断

# 快速修复
./xray_diagnostics.sh fix       # 自动修复常见问题
./xray_diagnostics.sh restart   # 重启所有服务
./xray_diagnostics.sh cleanup   # 清理系统
```

### 监控系统
```bash
# 启动监控（后台运行）
./xray_monitor.sh start --daemon

# 查看状态
./xray_monitor.sh status

# 停止监控
./xray_monitor.sh stop

# 重启特定服务
./xray_monitor.sh restart 端口号

# 删除所有服务
./xray_monitor.sh delete-all

# 查看日志
./xray_monitor.sh logs         # 监控日志
./xray_monitor.sh logs 端口号  # 服务日志
```

### SS链接工具
```bash
# 生成SS链接
./ss_link_utils.py generate -p 密码 -s 服务器 -P 端口 -n 节点名

# 解析SS链接
./ss_link_utils.py parse -l "ss://链接" -v

# 测试链接
./ss_link_utils.py test -l "ss://链接"

# 批量测试
./ss_link_utils.py batch-test -L "链接1" "链接2" "链接3"
```

### Web管理界面
```bash
cd web_prototype
pip install -r requirements.txt
python app.py
# 访问 http://localhost:5000
```

## 常见问题

### Q: 如何安装二维码支持？

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install qrencode

# CentOS/RHEL
sudo yum install qrencode

# macOS
brew install qrencode
```

### Q: 如何备份和恢复配置？

**使用内置功能（推荐）：**
```bash
# 在主菜单选择：
# 6. 备份配置 - 创建备份
# 7. 恢复配置 - 从备份恢复
# 8. 管理备份 - 管理备份文件
```

**手动备份：**
```bash
# 备份所有配置
tar -czf my_backup.tar.gz data/

# 恢复配置
tar -xzf my_backup.tar.gz
```

### Q: 备份文件在哪里？

备份文件保存在 `data/` 目录下：
- `xray_backup_YYYYMMDD_HHMMSS.tar.gz` - 手动备份
- `current_backup_YYYYMMDD_HHMMSS.tar.gz` - 恢复前自动备份

### Q: 服务无法启动怎么办？

1. 检查端口是否被占用：`netstat -tlnp | grep 端口号`
2. 查看错误日志：`cat data/services/端口号/xray.log`
3. 重启服务：在主菜单选择 "5. 重启所有服务"

### Q: 如何完全卸载？

```bash
# 停止所有服务
./xray_converter_simple.sh  # 选择删除所有服务

# 删除所有文件
rm -rf xray_converter_simple.sh xray data/
```

## 性能对比

| 方案 | 内存占用 | 启动时间 | 依赖 |
|------|----------|----------|------|
| Docker 版本 | 200-500MB | 10-30秒 | Docker |
| 本脚本 | 10-20MB | <1秒 | 无 |

## 技术支持

如遇问题，请提供：

1. 操作系统版本：`cat /etc/os-release`
2. 错误日志：`cat data/services/端口号/xray.log`
3. 系统资源：`free -h && df -h`

## 更新日志

### v2.1
- ✅ 添加节点名称标识功能
- ✅ 完整的备份恢复系统
- ✅ 备份文件管理功能
- ✅ 增强的服务列表显示
- ✅ 改进的用户界面

### v2.0
- ✅ 完全移除 Docker 依赖
- ✅ 添加二维码支持
- ✅ 添加有效期管理
- ✅ 优化内存占用
- ✅ 简化安装流程

### v1.0
- ✅ 基础 SOCKS5 转 SS 功能
- ✅ Docker 容器化部署

---

**推荐使用一键安装脚本获得最佳体验！**
