# 日历管理系统部署指南

本文档提供日历管理系统在生产环境中的完整部署步骤。

## 目录
1. [系统要求](#系统要求)
2. [安装步骤](#安装步骤)
3. [Nginx配置](#nginx配置)
4. [系统服务配置](#系统服务配置)
5. [安全配置](#安全配置)
6. [监控与维护](#监控与维护)

## 系统要求

- **操作系统**: Ubuntu 20.04+, CentOS 7+, 或其它 Linux 发行版
- **Python**: 3.7 或更高版本
- **数据库**: SQLite3 (内置)
- **Web服务器**: Nginx (推荐) 或 Apache
- **内存**: 至少 512MB RAM
- **磁盘空间**: 至少 100MB 可用空间

## 安装步骤

### 1. 克隆代码库
```bash
# 切换到web目录
cd /var/www
sudo git clone https://github.com/icanbot/calendar-management-system.git switchyomega/calendar
cd switchyomega/calendar
```

### 2. 安装Python依赖
```bash
# 安装所需的Python包
sudo pip3 install sqlite3  # 通常已内置

# 如果需要额外的包，创建requirements.txt
echo "python-dateutil" > requirements.txt
sudo pip3 install -r requirements.txt
```

### 3. 初始化数据库
```bash
# 运行初始化脚本
sudo python3 cgi-bin/init_db.py

# 或手动创建数据库目录
sudo mkdir -p data
sudo chown www-data:www-data data
```

### 4. 设置权限
```bash
# 设置目录权限
sudo chown -R www-data:www-data /var/www/switchyomega
sudo chmod -R 755 /var/www/switchyomega/calendar

# 创建上传目录
sudo mkdir -p uploads
sudo chown www-data:www-data uploads
```

## Nginx配置

### 1. 安装Nginx
```bash
sudo apt update
sudo apt install nginx -y
```

### 2. 配置站点
```bash
# 复制配置文件
sudo cp deployment/nginx-calendar.conf /etc/nginx/sites-available/calendar

# 启用站点
sudo ln -s /etc/nginx/sites-available/calendar /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx
```

### 3. 设置Basic认证（可选）
```bash
# 安装htpasswd工具
sudo apt install apache2-utils

# 创建认证文件
sudo htpasswd -c /etc/nginx/.htpasswd admin
# 输入密码

# 设置权限
sudo chown www-data:www-data /etc/nginx/.htpasswd
sudo chmod 640 /etc/nginx/.htpasswd
```

## 系统服务配置

### 1. 安装系统服务
```bash
# 复制服务文件
sudo cp deployment/calendar-server.service /etc/systemd/system/

# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务
sudo systemctl enable calendar-server

# 启动服务
sudo systemctl start calendar-server

# 检查状态
sudo systemctl status calendar-server
```

### 2. 服务管理命令
```bash
# 启动服务
sudo systemctl start calendar-server

# 停止服务
sudo systemctl stop calendar-server

# 重启服务
sudo systemctl restart calendar-server

# 查看日志
sudo journalctl -u calendar-server -f
```

## 安全配置

### 1. 修改默认凭证
**重要**: 修改 `app.py` 中的默认认证信息：
```python
# 在 app.py 中找到以下行并修改
USERNAME = "admin"          # 改为自定义用户名
PASSWORD = "Admin@2026"     # 改为强密码
```

### 2. 防火墙配置
```bash
# 允许HTTP/HTTPS流量
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable
```

### 3. SSL证书（HTTPS）
```bash
# 使用Certbot获取免费SSL证书
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 监控与维护

### 1. 健康检查脚本
```bash
# 复制监控脚本
sudo cp check-calendar.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/check-calendar.sh

# 设置定时任务（每小时检查）
sudo crontab -e
# 添加以下行：
0 * * * * /usr/local/bin/check-calendar.sh
```

### 2. 日志管理
```bash
# 查看应用日志
sudo journalctl -u calendar-server -n 50

# 查看监控日志
sudo tail -f /var/log/calendar-monitor.log

# 日志轮转配置（可选）
sudo cp deployment/logrotate-calendar /etc/logrotate.d/
```

### 3. 备份策略
```bash
# 创建备份脚本
sudo vim /usr/local/bin/backup-calendar.sh

# 内容示例：
#!/bin/bash
BACKUP_DIR="/backup/calendar"
DATE=$(date +%Y%m%d_%H%M%S)
cp /var/www/switchyomega/calendar/data/calendar.db "$BACKUP_DIR/calendar_$DATE.db"
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete

# 设置每日备份
sudo crontab -e
# 添加：
0 2 * * * /usr/local/bin/backup-calendar.sh
```

## 故障排除

### 常见问题

1. **服务无法启动**
   ```bash
   # 检查端口占用
   sudo netstat -tlnp | grep :8001
   
   # 检查Python错误
   sudo python3 app.py
   ```

2. **API返回500错误**
   ```bash
   # 检查数据库权限
   sudo ls -la /var/www/switchyomega/calendar/data/
   
   # 检查日志
   sudo journalctl -u calendar-server -n 100
   ```

3. **文件上传失败**
   ```bash
   # 检查上传目录权限
   sudo ls -la /var/www/switchyomega/calendar/uploads/
   
   # 检查磁盘空间
   df -h /var/www
   ```

### 获取帮助
- 查看详细文档: [README.md](../README.md)
- 报告问题: [GitHub Issues](https://github.com/icanbot/calendar-management-system/issues)
- 查看更新: `git pull origin main`

## 更新升级

```bash
# 拉取最新代码
cd /var/www/switchyomega/calendar
sudo git pull origin main

# 重启服务
sudo systemctl restart calendar-server

# 检查状态
sudo systemctl status calendar-server
```

---
**提示**: 定期检查安全更新，并备份重要数据。