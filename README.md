# Xray SOCKS5 to Shadowsocks Converter

一个将SOCKS5代理转换为Shadowsocks的工具，提供Web管理界面和命令行操作。

## 功能特性

- **SOCKS5转SS**: 将SOCKS5代理转换为Shadowsocks服务
- **Web管理界面**: 友好的Web界面管理所有服务
- **批量操作**: 支持批量添加、删除、重启服务
- **状态监控**: 实时监控服务状态和连接情况
- **自动化**: 自动下载Xray核心，自动配置生成

## 快速开始

### 命令行方式

```bash
# 克隆项目
git clone <项目地址>
cd xray-converter

# 运行脚本
./xray_converter_simple.sh
```

### Web界面

```bash
# 启动Web服务
cd web_prototype
python3 app.py

# 访问 http://localhost:5000
```

## 主要文件

- `xray_converter_simple.sh` - 主要的转换脚本
- `web_prototype/app.py` - Web管理界面
- `deploy.sh` - 一键部署脚本
- `service_monitor.sh` - 服务监控脚本
- `quick_diagnosis.sh` - 快速诊断脚本
- `install_native.sh` - 原生安装脚本

## 安装要求

- Linux/macOS/Windows
- Python 3.6+ (Web界面)
- curl, unzip (自动下载依赖)

## License

[Mozilla Public License Version 2.0](LICENSE)