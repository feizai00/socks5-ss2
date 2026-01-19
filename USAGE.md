# 使用指南

## 🚀 快速开始

### 一键部署（推荐）

```bash
# 下载并运行部署脚本
chmod +x deploy.sh
./deploy.sh
```

### 手动使用

```bash
# 直接运行转换器
chmod +x xray_converter_simple.sh
./xray_converter_simple.sh
```

## 📋 功能说明

### 1. 添加服务

1. **输入节点名称**
   ```
   用于标识此 SOCKS5 代理的名称

   示例:
   美国节点1
   香港VPS
   公司代理
   ```

2. **输入 SOCKS5 代理信息**
   ```
   格式1: IP:端口                    # 无认证
   格式2: IP:端口:用户名:密码         # 有认证

   示例:
   149.119.147.4:44496
   149.119.147.4:44496:user:pass
   ```

3. **选择有效期**
   - 1) 永久有效
   - 2) 7天
   - 3) 30天
   - 4) 90天
   - 5) 自定义天数

4. **获取连接信息**
   - 自动生成 SS 端口和密码
   - 显示完整连接信息
   - 生成二维码（需安装 qrencode）
   - 提供 SS 连接链接

### 2. 列出服务

显示所有服务的状态信息：
- 端口号
- 运行状态（运行中/已停止/已过期）
- 后端代理地址
- 有效期

### 3. 查看服务详情

输入端口号查看完整信息：
- 连接参数（服务器、端口、密码、加密）
- 服务状态和有效期
- 后端代理信息
- SS 连接链接和二维码

### 4. 删除服务

安全删除指定端口的服务：
- 停止 Xray 进程
- 删除配置文件
- 清理相关数据

### 4.5. 删除所有服务

一键删除所有服务（需要三重确认）：
- 显示所有将被删除的服务
- 三重确认保护（输入 DELETE + YES + 服务数量）
- 自动创建删除前备份
- 停止监控服务
- 批量删除所有服务和配置

### 6. 备份配置

创建当前所有服务配置的备份：
- 自动时间戳命名
- 压缩存储节省空间
- 显示备份文件信息

### 7. 恢复配置

从备份文件恢复服务配置：
- 列出可用备份文件
- 支持手动指定备份路径
- 恢复前自动备份当前配置
- 自动启动恢复的服务

### 8. 管理备份

管理备份文件：
- 查看所有备份文件
- 删除指定备份
- 清理旧备份（保留最新5个）
- 显示备份文件大小和时间

## 🔧 高级功能

### 二维码支持

安装 qrencode 后可显示连接二维码：

```bash
# Ubuntu/Debian
sudo apt install qrencode

# CentOS/RHEL  
sudo yum install qrencode

# macOS
brew install qrencode
```

### 有效期管理

- **永久有效**: 服务不会过期
- **定期有效**: 到期后自动标记为"已过期"
- **自定义**: 可设置任意天数

过期服务仍会显示在列表中，但状态为"已过期"。

### 日志查看

```bash
# 查看指定服务日志
cat data/services/端口号/xray.log

# 实时监控日志
tail -f data/services/端口号/xray.log
```

## 📱 客户端配置

### 连接信息示例

```
节点名称: 美国节点1
服务器地址: 1.2.3.4
端口: 12345
密码: abcd1234efgh
加密方式: aes-256-gcm
有效期至: 2024-02-15 10:30:00
剩余天数: 15 天
```

### 推荐客户端

| 平台 | 推荐客户端 |
|------|------------|
| Windows | Shadowsocks-Windows, v2rayN |
| macOS | ShadowsocksX-NG, ClashX |
| iOS | Shadowrocket, Quantumult X |
| Android | Shadowsocks Android, v2rayNG |

### 导入方式

1. **手动配置**: 输入连接信息
2. **扫描二维码**: 使用客户端扫码功能
3. **导入链接**: 复制 SS 链接到客户端

## 🛠️ 故障排除

### 常见问题

**Q: 服务无法启动**
```bash
# 检查端口占用
netstat -tlnp | grep 端口号

# 查看错误日志
cat data/services/端口号/xray.log

# 重新启动服务
./xray_converter.sh  # 选择删除后重新添加
```

**Q: 无法连接到服务**
```bash
# 检查防火墙
sudo ufw status
sudo firewall-cmd --list-ports

# 检查服务状态
./xray_converter.sh  # 选择"2. 列出服务"
```

**Q: 二维码无法显示**
```bash
# 安装 qrencode
sudo apt install qrencode  # Ubuntu/Debian
sudo yum install qrencode  # CentOS/RHEL
```

**Q: 备份创建失败**
```bash
# 检查磁盘空间
df -h

# 检查权限
ls -la data/

# 手动创建备份
tar -czf manual_backup.tar.gz data/services/
```

**Q: 恢复失败**
```bash
# 检查备份文件完整性
tar -tzf backup_file.tar.gz

# 查看详细错误信息
tar -xzf backup_file.tar.gz -v

# 手动恢复
mkdir -p data/
tar -xzf backup_file.tar.gz -C data/
```

### 完全重置

```bash
# 停止所有服务
./xray_converter.sh  # 逐个删除所有服务

# 删除所有数据
rm -rf data/

# 重新初始化
./xray_converter.sh
```

## 📊 性能优势

| 指标 | Docker版本 | 本脚本 |
|------|------------|--------|
| 内存占用 | 200-500MB | 10-20MB |
| 启动时间 | 10-30秒 | <1秒 |
| 磁盘占用 | 500MB+ | 50MB |
| 依赖复杂度 | 高 | 无 |

## 🔒 安全建议

1. **定期更新**: 定期重新下载最新版本
2. **防火墙**: 只开放必要的端口
3. **有效期**: 为临时使用设置有效期
4. **监控**: 定期检查服务状态和日志

## 📦 备份与恢复

### 使用内置功能（推荐）

```bash
# 启动脚本
./xray_converter.sh

# 选择相应功能：
# 6. 备份配置 - 创建备份
# 7. 恢复配置 - 从备份恢复
# 8. 管理备份 - 管理备份文件
```

### 手动备份

```bash
# 备份所有配置
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# 备份到远程
scp backup_*.tar.gz user@remote:/backup/

# 查看备份内容
tar -tzf backup_*.tar.gz
```

### 手动恢复

```bash
# 停止所有服务
./xray_converter.sh  # 逐个删除服务

# 恢复配置
tar -xzf backup_*.tar.gz

# 重启脚本自动检测并启动服务
./xray_converter.sh
```

### 备份文件说明

- `xray_backup_YYYYMMDD_HHMMSS.tar.gz` - 手动创建的备份
- `current_backup_YYYYMMDD_HHMMSS.tar.gz` - 恢复前自动备份
- 备份文件包含所有服务配置和节点信息
- 支持跨服务器迁移

---

**提示**: 建议使用一键部署脚本 `deploy.sh` 获得最佳体验！
