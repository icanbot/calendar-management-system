#!/bin/bash
# 日历管理系统 - GitHub 部署脚本
# 使用方法：修改下面的变量，然后运行 ./deploy-to-github.sh

# ===================== 配置区域 =====================
# 请修改以下变量为你自己的信息

# GitHub 用户名（必填）
GITHUB_USERNAME="YOUR_GITHUB_USERNAME"

# 仓库名称（默认为 calendar-management-system）
REPO_NAME="calendar-management-system"

# 仓库描述（可选）
REPO_DESCRIPTION="A comprehensive calendar management system with file upload and email integration"

# 仓库可见性：public 或 private
REPO_VISIBILITY="public"

# 分支名称：main 或 master
BRANCH_NAME="main"

# 远程仓库类型：https 或 ssh
REMOTE_TYPE="ssh"  # 或 "https"

# GitHub 个人访问令牌（仅当使用 HTTPS 且需要认证时）
# 可以在 GitHub Settings → Developer settings → Personal access tokens 创建
GITHUB_TOKEN=""

# ===================== 脚本开始 =====================
set -e  # 遇到错误时退出脚本

echo "🚀 开始部署日历管理系统到 GitHub..."
echo "=========================================="

# 检查当前目录是否为 Git 仓库
if [ ! -d ".git" ]; then
    echo "❌ 当前目录不是 Git 仓库"
    echo "请先运行：git init"
    exit 1
fi

# 检查是否有未提交的更改
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 发现有未提交的更改"
    read -p "是否要提交这些更改？(y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add .
        git commit -m "Auto-commit before deployment"
    else
        echo "❌ 请先提交或暂存更改"
        exit 1
    fi
fi

# 配置远程仓库 URL
if [ "$REMOTE_TYPE" = "ssh" ]; then
    REMOTE_URL="git@github.com:${GITHUB_USERNAME}/${REPO_NAME}.git"
else
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "⚠️  使用 HTTPS 但未提供 GitHub Token"
        echo "将使用基本认证（可能需要输入密码）"
        REMOTE_URL="https://github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"
    else
        REMOTE_URL="https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"
    fi
fi

echo "📦 仓库信息："
echo "  - 用户名：$GITHUB_USERNAME"
echo "  - 仓库名：$REPO_NAME"
echo "  - 远程URL：$REMOTE_URL"
echo "  - 分支：$BRANCH_NAME"

# 检查是否已配置远程仓库
if git remote | grep -q origin; then
    echo "🔄 已存在远程仓库 origin，更新 URL..."
    git remote set-url origin "$REMOTE_URL"
else
    echo "➕ 添加远程仓库 origin..."
    git remote add origin "$REMOTE_URL"
fi

# 重命名分支（如果需要）
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH_NAME" ]; then
    echo "🔄 重命名分支 $CURRENT_BRANCH → $BRANCH_NAME"
    git branch -M "$BRANCH_NAME"
fi

# 检查 GitHub CLI 是否可用
if command -v gh &> /dev/null; then
    echo "🔧 检测到 GitHub CLI，尝试创建仓库（如果不存在）..."
    
    # 检查仓库是否已存在
    if gh repo view "${GITHUB_USERNAME}/${REPO_NAME}" &> /dev/null; then
        echo "✅ 仓库已存在，跳过创建"
    else
        echo "📝 创建新仓库..."
        gh repo create "$REPO_NAME" \
            --"$REPO_VISIBILITY" \
            --description "$REPO_DESCRIPTION" \
            --source=. \
            --remote=origin \
            --push
        echo "✅ 仓库创建成功并已推送"
        exit 0
    fi
else
    echo "ℹ️  GitHub CLI 未安装，跳过自动创建仓库"
    echo "请确保已在 GitHub 上创建仓库：https://github.com/new"
    read -p "是否已在 GitHub 创建仓库 $REPO_NAME？(y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ 请先在 GitHub 创建仓库"
        echo "访问：https://github.com/new"
        exit 1
    fi
fi

# 推送代码
echo "⬆️  推送代码到 GitHub..."
if git push -u origin "$BRANCH_NAME"; then
    echo "✅ 推送成功！"
else
    echo "❌ 推送失败，可能的原因："
    echo "   1. 远程仓库不存在"
    echo "   2. 认证失败"
    echo "   3. 网络问题"
    echo ""
    echo "🔄 尝试强制推送（仅在首次推送时使用）..."
    read -p "是否尝试强制推送？(y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git push -u origin "$BRANCH_NAME" --force
        echo "✅ 强制推送成功"
    else
        echo "❌ 推送中止，请手动检查问题"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "🎉 部署完成！"
echo ""
echo "你的日历管理系统代码已推送到："
echo "🔗 https://github.com/${GITHUB_USERNAME}/${REPO_NAME}"
echo ""
echo "下一步操作建议："
echo "1. 访问上述链接确认代码已上传"
echo "2. 在仓库设置中启用 Issues 和 Wiki"
echo "3. 添加项目描述和 README 徽章"
echo "4. 邀请团队成员协作"
echo "5. 考虑设置 CI/CD 自动化"
echo ""
echo "📚 更多帮助请查看 DEPLOY.md 文件"