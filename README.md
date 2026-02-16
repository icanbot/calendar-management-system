# 日历管理系统 (Calendar Management System)

一个功能完整的日程管理Web应用，支持事件管理、文件上传、邮件集成和自动提醒。

## 🌟 功能特性

### 📅 事件管理
- 创建、读取、更新、删除日历事件
- 事件分类（会议、工作、个人、其他）
- 全天事件支持
- 参与者管理

### 🔔 智能提醒
- 飞书自动提醒（提前30分钟）
- 支持自定义提醒时间
- 系统心跳检查（每小时）

### 📎 文件管理
- 多格式文件上传（multipart/form-data 和 base64）
- 文件列表查看与删除
- Excel模板下载（项目月度工作计划）
- 安全文件存储

### 📧 邮箱集成
- 邮件发送功能（SMTP）
- 收件箱检查（IMAP）
- 未读邮件统计

### 🛡️ 安全特性
- HTTP Basic 认证
- 防止路径遍历攻击
- 文件类型验证
- 安全的数据库操作

### 🌐 前端界面
- 响应式设计（支持移动端）
- FullCalendar 日历视图
- Bootstrap 5 UI 框架
- Font Awesome 图标

## 🚀 快速开始

### 环境要求
- Python 3.7+
- SQLite3
- Nginx（反向代理）

### 安装步骤

1. **克隆仓库**
```bash
git clone <repository-url>
cd calendar
```

2. **配置环境**
```bash
# 创建上传目录
mkdir -p uploads

# 创建数据目录
mkdir -p data

# 初始化数据库
python3 cgi-bin/init_db.py
```

3. **启动服务**
```bash
# 直接运行（开发环境）
python3 app.py

# 使用systemd（生产环境）
sudo cp calendar-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable calendar-server
sudo systemctl start calendar-server
```

4. **配置Nginx**
```nginx
location /calendar/ {
    proxy_pass http://localhost:8001/;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_pass_header Authorization;
    client_max_body_size 10M;
}
```

### 配置文件
复制 `config.example.json` 到 `config.json` 并修改：
- 数据库路径
- 上传目录
- 认证信息

## 📁 项目结构

```
calendar/
├── app.py                    # 主应用服务器
├── index.html               # 日历前端
├── upload.html              # 文件上传页面
├── example_upload.py        # 文件上传示例
├── cgi-bin/
│   ├── events_api.py        # CGI事件API（旧版）
│   └── init_db.py           # 数据库初始化
├── data/                    # 数据库目录（不提交）
├── uploads/                 # 上传文件目录（不提交）
├── static/                  # 静态资源
└── README.md                # 本文档
```

## 🔧 API 接口

### 事件管理
- `GET /api/events` - 获取所有事件
- `GET /api/events/today` - 获取今日事件
- `GET /api/events/upcoming` - 获取即将发生的事件
- `POST /api/events` - 创建事件
- `PUT /api/events/{id}` - 更新事件
- `DELETE /api/events/{id}` - 删除事件

### 文件管理
- `GET /api/uploads` - 获取文件列表
- `POST /api/upload` - 上传文件（multipart）
- `POST /api/upload_base64` - 上传文件（base64）
- `DELETE /api/uploads/{filename}` - 删除文件

## 📊 数据库架构

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    location TEXT,
    participants TEXT,
    status TEXT DEFAULT 'scheduled',
    reminder_minutes INTEGER DEFAULT 30,
    is_all_day BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## 🔒 安全注意事项

1. **认证信息**
   - 默认用户名：`admin`
   - 默认密码：`Admin@2026`
   - 生产环境请务必修改

2. **文件上传**
   - 限制文件类型
   - 验证文件大小（最大10MB）
   - 防止路径遍历攻击

3. **数据库**
   - 使用参数化查询防止SQL注入
   - 定期备份重要数据

## 🚢 部署指南

### Docker 部署（可选）
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8001
CMD ["python", "app.py"]
```

### 系统服务
```bash
# 创建systemd服务
sudo vim /etc/systemd/system/calendar-server.service

# 内容参考：
[Unit]
Description=Calendar Management System Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/switchyomega/calendar
ExecStart=/usr/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📞 支持与联系

如有问题或建议，请提交 [Issue](https://github.com/icanbot/calendar-management-system/issues) 或通过邮件联系。

---

**提示**: 请确保在生产环境中修改默认的认证信息，并定期更新依赖包以确保安全。