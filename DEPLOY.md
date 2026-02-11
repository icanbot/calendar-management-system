# 部署到 GitHub 指南

本指南帮助你将日历管理系统代码推送到 GitHub 仓库。

## 前提条件

1. **GitHub 账户**
   - 如果没有，请先注册 [GitHub](https://github.com)

2. **Git 客户端**
   - 确保已安装 Git
   - 配置用户名和邮箱：
   ```bash
   git config --global user.name "你的名字"
   git config --global user.email "你的邮箱"
   ```

## 方法一：创建新仓库并推送（推荐）

### 步骤 1：在 GitHub 创建新仓库

1. 登录 GitHub
2. 点击右上角 "+" → "New repository"
3. 填写仓库信息：
   - Repository name: `calendar-management-system`（或自定义名称）
   - Description: 可选的描述
   - Public / Private: 根据需要选择
   - **不要** 初始化 README、.gitignore 或许可证
4. 点击 "Create repository"

### 步骤 2：添加远程仓库并推送

复制仓库的 HTTPS 或 SSH URL，然后在本目录执行：

```bash
# 添加远程仓库（替换 YOUR_USERNAME 和 REPO_NAME）
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# 或者使用 SSH（推荐）
git remote add origin git@github.com:YOUR_USERNAME/REPO_NAME.git

# 重命名分支为 main（如果 GitHub 使用 main）
git branch -M main

# 推送代码
git push -u origin main
```

### 步骤 3：验证推送

访问你的 GitHub 仓库页面，确认代码已上传。

## 方法二：使用 GitHub CLI（更简单）

如果你安装了 GitHub CLI：

```bash
# 登录
gh auth login

# 创建仓库并推送
gh repo create calendar-management-system --public --source=. --remote=origin --push
```

## 方法三：使用自动化脚本

我们提供了一个脚本模板，帮助你快速推送：

1. **编辑脚本**：修改 `deploy-to-github.sh` 中的变量
2. **运行脚本**：
```bash
chmod +x deploy-to-github.sh
./deploy-to-github.sh
```

## 常见问题

### 1. 认证失败
```bash
# 如果使用 HTTPS 遇到认证问题：
# 方法 A：使用个人访问令牌（推荐）
# - 在 GitHub Settings → Developer settings → Personal access tokens 创建令牌
# - 在推送时使用令牌作为密码

# 方法 B：切换到 SSH
git remote set-url origin git@github.com:YOUR_USERNAME/REPO_NAME.git

# 方法 C：使用凭据管理器
git config --global credential.helper store
```

### 2. 分支名称冲突
```bash
# 如果远程使用 main，本地使用 master
git branch -M main
git push -u origin main
```

### 3. 忽略的文件被推送
```bash
# 检查 .gitignore 是否生效
git status --ignored

# 从仓库中删除已提交的敏感文件
git rm --cached data/calendar.db
git commit -m "Remove database file"
git push
```

## 后续维护

### 更新代码
```bash
# 修改代码后
git add .
git commit -m "描述更改内容"
git push
```

### 从 GitHub 拉取更新
```bash
git pull origin main
```

### 添加标签（版本发布）
```bash
git tag v1.0.0
git push origin v1.0.0
```

## 安全提醒

⚠️ **重要**：在推送前确保没有包含敏感信息：

1. **数据库文件**：`data/calendar.db` 已被 .gitignore 排除
2. **上传的文件**：`uploads/` 目录已被排除
3. **配置文件**：检查是否包含密码、API密钥等
4. **日志文件**：`server.log` 已被排除

可以使用以下命令检查：
```bash
# 查看将要推送的文件
git ls-files

# 搜索可能包含敏感信息的文件
grep -r "password\|token\|key\|secret" . --include="*.py" --include="*.json" --include="*.txt"
```

## 高级配置

### GitHub Actions 自动部署
在 `.github/workflows/deploy.yml` 中添加自动化部署流程。

### 使用 GitHub Pages 展示文档
启用 GitHub Pages 展示 `README.md` 和项目文档。

## 获取帮助

- GitHub 文档：https://docs.github.com
- Git 文档：https://git-scm.com/doc
- 问题反馈：在仓库 Issues 中提出

---

完成推送后，你可以：
1. 邀请团队成员协作
2. 设置 CI/CD 流水线
3. 添加许可证
4. 创建发布版本