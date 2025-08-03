# 🚀 Xray转换器 - 部署指南

本项目提供多种部署方式，支持从GitHub一键部署到服务器。

## 📋 部署方式对比

| 部署方式 | 适用场景 | 难度 | 自动化程度 |
|---------|----------|------|------------|
| **GitHub Actions** | 生产环境、CI/CD | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **一键部署脚本** | 快速部署 | ⭐ | ⭐⭐⭐⭐ |
| **手动部署** | 自定义需求 | ⭐⭐⭐ | ⭐⭐ |

## 🎯 方案1: GitHub Actions 自动部署 (推荐)

### 1.1 准备工作

1. **创建GitHub仓库**:
   ```bash
   # 在GitHub创建新仓库，然后执行:
   git remote add origin https://github.com/你的用户名/xray-converter.git
   git push -u origin main
   ```

2. **配置GitHub Secrets**:
   在GitHub仓库的 `Settings > Secrets and variables > Actions` 中添加:
   
   | Secret Name | 说明 | 示例 |
   |-------------|------|------|
   | `SSH_PRIVATE_KEY` | 服务器SSH私钥 | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
   | `SERVER_HOST` | 服务器IP或域名 | `1.2.3.4` 或 `your-server.com` |

### 1.2 生成SSH密钥

在本地生成SSH密钥对:
```bash
# 生成SSH密钥对
ssh-keygen -t rsa -b 4096 -C "deploy@xray-converter" -f ~/.ssh/xray_deploy

# 将公钥添加到服务器
ssh-copy-id -i ~/.ssh/xray_deploy.pub root@your-server-ip

# 将私钥内容复制到GitHub Secrets
cat ~/.ssh/xray_deploy
```

### 1.3 触发部署

1. **自动部署**: 推送代码到 `main` 分支时自动触发
   ```bash
   git add .
   git commit -m "🚀 部署到生产环境"
   git push origin main
   ```

2. **手动部署**: 在GitHub仓库的 `Actions` 页面手动触发
   - 点击 `🚀 Deploy to Server`
   - 点击 `Run workflow`
   - 输入服务器信息并运行

### 1.4 部署结果

部署完成后，你将获得:
- ✅ systemd服务 (`xray-converter-web`)
- ✅ Nginx反向代理 (端口80)
- ✅ 自动重启和日志管理
- ✅ Web界面: `http://your-server-ip`

## 🚀 方案2: 一键部署脚本

### 2.1 准备服务器

确保服务器满足以下条件:
- Ubuntu 18.04+ / CentOS 7+ / Debian 10+
- 2GB+ 内存
- 10GB+ 磁盘空间
- SSH访问权限

### 2.2 执行部署

1. **交互式部署**:
   ```bash
   ./deploy-quick.sh
   ```
   
   按提示输入:
   - GitHub仓库地址 (如: `username/xray-converter`)
   - 服务器IP或域名
   - 部署用户 (默认: `root`)
   - 部署路径 (默认: `/opt/xray-converter`)
   - 服务端口 (默认: `9090`)

2. **环境变量部署**:
   ```bash
   GITHUB_REPO="username/xray-converter" \
   DEPLOY_HOST="1.2.3.4" \
   DEPLOY_USER="root" \
   ./deploy-quick.sh
   ```

### 2.3 部署时间

整个部署过程约需要 **5-10分钟**，包括:
- ⏱️ 系统依赖安装 (2-3分钟)
- ⏱️ Python环境配置 (1-2分钟)
- ⏱️ 服务配置和启动 (1-2分钟)
- ⏱️ Web界面测试 (1分钟)

## 🛠 方案3: 手动部署

### 3.1 服务器准备

```bash
# 更新系统
apt update && apt upgrade -y  # Ubuntu/Debian
# 或
yum update -y  # CentOS/RHEL

# 安装依赖
apt install -y python3 python3-pip python3-venv curl unzip nginx git
# 或
yum install -y python3 python3-pip curl unzip nginx git
```

### 3.2 下载代码

```bash
# 克隆仓库
git clone https://github.com/username/xray-converter.git
cd xray-converter

# 或者使用现有的部署脚本
DEPLOY_HOST=localhost ./deploy_server.sh deploy
```

### 3.3 配置服务

```bash
# 创建Python虚拟环境
cd web_prototype
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置systemd服务
sudo cp ../deploy/xray-converter-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable xray-converter-web
sudo systemctl start xray-converter-web

# 配置Nginx
sudo cp ../deploy/nginx.conf /etc/nginx/sites-available/xray-converter
sudo ln -s /etc/nginx/sites-available/xray-converter /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

## 📊 部署后管理

### 服务管理命令

```bash
# 查看服务状态
systemctl status xray-converter-web

# 重启服务
systemctl restart xray-converter-web

# 查看日志
journalctl -u xray-converter-web -f

# 查看最近100行日志
journalctl -u xray-converter-web -n 100
```

### 更新部署

```bash
# 方式1: 重新运行GitHub Actions

# 方式2: 使用部署脚本更新
ssh root@your-server "cd /opt/xray-converter && git pull && systemctl restart xray-converter-web"

# 方式3: 重新运行一键部署脚本
./deploy-quick.sh
```

## 🔧 常见问题

### Q: 部署失败，如何排查？

**A: 按以下步骤排查:**

1. **检查SSH连接**:
   ```bash
   ssh root@your-server-ip "echo 'SSH测试成功'"
   ```

2. **检查服务状态**:
   ```bash
   ssh root@your-server-ip "systemctl status xray-converter-web"
   ```

3. **查看详细日志**:
   ```bash
   ssh root@your-server-ip "journalctl -u xray-converter-web -n 50"
   ```

### Q: Web界面无法访问？

**A: 检查以下项目:**

1. **防火墙设置**:
   ```bash
   # Ubuntu/Debian
   ufw allow 80
   ufw allow 9090
   
   # CentOS/RHEL
   firewall-cmd --permanent --add-port=80/tcp
   firewall-cmd --permanent --add-port=9090/tcp
   firewall-cmd --reload
   ```

2. **Nginx状态**:
   ```bash
   systemctl status nginx
   nginx -t  # 检查配置
   ```

3. **服务端口**:
   ```bash
   netstat -tlnp | grep :80
   netstat -tlnp | grep :9090
   ```

### Q: 如何更改Web端口？

**A: 修改配置文件:**

1. **修改应用配置**:
   ```bash
   # 编辑 web_prototype/app.py
   # 将 port=9090 改为你想要的端口
   ```

2. **修改Nginx配置**:
   ```bash
   # 编辑 /etc/nginx/sites-available/xray-converter
   # 修改 proxy_pass 中的端口号
   ```

3. **重启服务**:
   ```bash
   systemctl restart xray-converter-web
   systemctl restart nginx
   ```

## 🎯 性能优化

### 服务器配置建议

| 用户规模 | CPU | 内存 | 磁盘 | 带宽 |
|---------|-----|------|------|------|
| **小型** (1-10个服务) | 1核 | 1GB | 20GB | 10Mbps |
| **中型** (10-50个服务) | 2核 | 2GB | 50GB | 50Mbps |
| **大型** (50+个服务) | 4核 | 4GB | 100GB | 100Mbps |

### 系统优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# 优化内核参数
echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 65535" >> /etc/sysctl.conf
sysctl -p
```

## 🚀 推送项目到GitHub

### 方法1: 使用命令行推送

```bash
# 添加远程仓库
git remote add origin https://github.com/你的用户名/仓库名.git

# 推送代码
git push -u origin main
```

### 方法2: 使用GitHub网页上传

1. 在仓库页面点击 "uploading an existing file"
2. 拖拽项目文件到页面
3. 添加提交信息并提交

## 📞 技术支持

如果遇到问题，可以通过以下方式获取帮助:

1. **查看文档**: `README.md` 和 `USAGE.md`
2. **运行诊断**: `./quick_diagnosis.sh`
3. **GitHub Issues**: 在项目仓库提交问题
4. **日志分析**: 查看详细的服务日志

---

**🎉 恭喜！你现在已经成功部署了 Xray SOCKS5 to Shadowsocks 转换器！**

访问 `http://your-server-ip` 开始使用 Web 管理界面。