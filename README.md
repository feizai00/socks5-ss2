# 🚀 Xray SOCKS5 to Shadowsocks Converter

将SOCKS5代理转换为Shadowsocks服务，提供Web管理界面。

## ✨ 核心功能

- 🔄 **SOCKS5 → Shadowsocks** 协议转换
- 🌐 **Web管理界面** (端口9090)
- ⚡ **一键部署** 到服务器
- 📊 **服务监控** 和批量管理

## 🚀 快速开始

### 本地使用
```bash
git clone https://github.com/feizai00/socks5-ss2.git
cd socks5-ss2
./xray_converter_simple.sh
```

### 一键部署到服务器
```bash
curl -sSL https://raw.githubusercontent.com/feizai00/socks5-ss2/main/deploy-quick.sh | bash
```

### Web界面
```bash
cd web_prototype
./quick_fix.sh  # 自动配置环境
```
访问: `http://你的IP:9090` (admin/admin123)

## 📁 项目结构

```
📦 socks5-ss2/
├── 🚀 xray_converter_simple.sh  # 主转换脚本
├── 📱 deploy-quick.sh           # 一键部署
├── 🌐 web_prototype/           # Web管理界面
├── 🛠️ quick_diagnosis.sh      # 系统诊断
└── 📚 DEPLOY.md               # 详细部署指南
```

## 📋 系统要求

- **系统**: Linux/macOS/Windows
- **Python**: 3.6+ (Web界面)
- **依赖**: curl, unzip (自动安装)

## 📖 详细文档

- [部署指南](DEPLOY.md) - 完整部署说明
- [使用手册](USAGE.md) - 功能介绍

## 📄 许可证

[Mozilla Public License Version 2.0](LICENSE)