# 服务器部署指南

## 📦 打包文件说明

打包文件：`xray-converter-optimized-20250829.tar.gz` (约18MB)

**包含内容：**
- ✅ 所有核心脚本和工具
- ✅ Web管理界面
- ✅ 文档和配置文件
- ✅ Xray二进制文件
- ✅ 地理位置数据文件

**排除内容：**
- ❌ Git版本控制文件
- ❌ 系统缓存文件
- ❌ 运行时数据
- ❌ Python虚拟环境
- ❌ 数据库文件

## 🚀 服务器部署步骤

### 1. 上传和解压

```bash
# 上传文件到服务器
scp xray-converter-optimized-20250829.tar.gz user@your-server:/home/user/

# 连接服务器
ssh user@your-server

# 解压文件
cd /home/user
tar -xzf xray-converter-optimized-20250829.tar.gz

# 进入项目目录
cd xray-converter
```

### 2. 检查系统环境

```bash
# 检查操作系统
uname -a

# 检查必要依赖
which curl wget unzip python3

# 如果缺少依赖，安装它们
# Ubuntu/Debian:
sudo apt update && sudo apt install curl wget unzip python3 python3-pip qrencode

# CentOS/RHEL:
sudo yum install curl wget unzip python3 python3-pip qrencode

# 或者使用新的包管理器
sudo dnf install curl wget unzip python3 python3-pip qrencode
```

### 3. 设置权限

```bash
# 设置脚本执行权限
chmod +x *.sh *.py

# 检查权限
ls -la *.sh *.py
```

### 4. 快速启动测试

**方法1：使用安装脚本（推荐）**
```bash
./install_native.sh
```

**方法2：直接运行主脚本**
```bash
./xray_converter_simple.sh
```

### 5. Web界面部署（可选）

```bash
# 进入Web目录
cd web_prototype

# 安装Python依赖
pip3 install -r requirements.txt

# 启动Web服务
python3 app.py

# 访问 http://your-server-ip:5000
```

## 🛠️ 功能测试

### 基础功能测试
```bash
# 1. 测试主脚本
./xray_converter_simple.sh

# 2. 测试诊断工具
./xray_diagnostics.sh system

# 3. 测试监控系统
./xray_monitor.sh status

# 4. 测试SS链接工具
./ss_link_utils.py --help
```

### 网络测试
```bash
# 检查端口可用性
netstat -tlnp | grep LISTEN

# 检查防火墙状态
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-ports  # CentOS
```

## 🔧 优化建议

### 系统优化
```bash
# 增加文件描述符限制
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# 优化网络参数
echo "net.core.somaxconn = 65536" | sudo tee -a /etc/sysctl.conf
echo "net.core.netdev_max_backlog = 5000" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 防火墙配置
```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 5000/tcp  # Web界面
sudo ufw allow 10000:65535/tcp  # 服务端口范围
sudo ufw enable

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=22/tcp
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --permanent --add-port=10000-65535/tcp
sudo firewall-cmd --reload
```

## 📊 监控和维护

### 启动监控服务
```bash
# 启动后台监控
./xray_monitor.sh start --daemon

# 检查监控状态
./xray_monitor.sh status

# 查看日志
./xray_monitor.sh logs
```

### 日常维护
```bash
# 备份配置
./xray_converter_simple.sh  # 选择备份功能

# 系统诊断
./xray_diagnostics.sh all

# 清理系统
./xray_diagnostics.sh cleanup
```

## 🔍 故障排除

### 常见问题

**1. 权限问题**
```bash
# 重新设置权限
chmod +x *.sh *.py
sudo chown -R $USER:$USER .
```

**2. 端口被占用**
```bash
# 检查端口占用
netstat -tlnp | grep :端口号
sudo lsof -i :端口号

# 杀死占用进程
sudo kill -9 PID
```

**3. Xray下载失败**
```bash
# 手动下载 (如果自动下载失败)
wget https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip
unzip Xray-linux-64.zip
chmod +x xray
```

**4. 依赖缺失**
```bash
# Python依赖
pip3 install flask psutil

# 系统依赖
sudo apt install qrencode  # 二维码支持
```

### 日志文件位置
- 监控日志：`data/monitor.log`
- 服务日志：`data/services/端口号/xray.log`
- Web日志：`web_prototype/xray_web.log`

## 🎯 性能优化

### 内存优化
- 每个服务约占用 10-20MB 内存
- 建议服务器至少 512MB 内存
- 可同时运行 20+ 个服务

### CPU优化
- Xray对CPU要求不高
- 1核CPU可支持多个服务
- 建议启用监控自动重启

### 存储优化
- 定期清理日志文件
- 删除旧备份文件
- 监控磁盘使用情况

## 📞 技术支持

如遇问题，请提供：
1. 系统信息：`uname -a && cat /etc/os-release`
2. 错误日志：相关日志文件内容
3. 网络状态：`netstat -tlnp`
4. 资源使用：`free -h && df -h`

---

**部署完成后，建议先添加一个测试服务验证功能正常！**