# 使用说明

## 命令行使用

### 1. 基本操作

```bash
# 添加服务
./xray_converter_simple.sh add

# 列出所有服务
./xray_converter_simple.sh list

# 查看服务详情
./xray_converter_simple.sh view <端口>

# 停止服务
./xray_converter_simple.sh stop <端口>

# 删除服务
./xray_converter_simple.sh delete <端口>
```

### 2. 监控和诊断

```bash
# 启动监控
./service_monitor.sh

# 快速诊断
./quick_diagnosis.sh

# 一键部署
./deploy.sh
```

## Web界面使用

### 1. 启动Web服务

```bash
cd web_prototype
python3 app.py
```

### 2. 访问界面

在浏览器中访问 `http://localhost:5000`

默认登录信息:
- 用户名: admin
- 密码: admin123

### 3. 主要功能

- **服务管理**: 添加、删除、启动、停止服务
- **状态监控**: 实时查看服务状态和连接数
- **批量操作**: 一键重启所有服务
- **日志查看**: 查看服务运行日志
- **配置编辑**: 在线编辑服务配置

## 注意事项

1. 确保有足够的权限运行脚本
2. 防火墙需要开放对应端口
3. 定期备份配置文件
4. 监控服务资源使用情况