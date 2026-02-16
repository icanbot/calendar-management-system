#!/bin/bash
# 日程管理系统健康检查脚本
# 每小时运行一次，检查服务状态并自动修复

set -e

# 配置变量 - 请根据实际情况修改
LOG_FILE="/var/log/calendar-monitor.log"
SERVICE_NAME="calendar-server"
API_URL="http://localhost:8001/api/events"
# 认证信息 - 请修改为实际的用户名和密码
AUTH="admin:Admin@2026"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_service() {
    # 检查systemd服务状态
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log "服务 $SERVICE_NAME 运行中"
        return 0
    else
        log "服务 $SERVICE_NAME 未运行"
        return 1
    fi
}

check_api() {
    # 检查API是否可达
    local timeout=10
    local status_code
    
    status_code=$(curl -u "$AUTH" -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$API_URL" 2>/dev/null || echo "000")
    
    if [ "$status_code" = "200" ]; then
        log "API接口正常 (HTTP $status_code)"
        return 0
    else
        log "API接口异常 (HTTP $status_code)"
        return 1
    fi
}

restart_service() {
    log "正在重启服务 $SERVICE_NAME..."
    
    # 停止服务
    if systemctl stop "$SERVICE_NAME" 2>/dev/null; then
        log "服务停止成功"
    else
        log "服务停止失败"
    fi
    
    # 等待确保进程结束
    sleep 2
    
    # 启动服务
    if systemctl start "$SERVICE_NAME" 2>/dev/null; then
        log "服务启动命令已发送"
    else
        log "服务启动命令失败"
        return 1
    fi
    
    # 等待服务启动
    sleep 5
    
    # 检查是否启动成功
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log "服务重启成功"
        return 0
    else
        log "服务重启失败"
        return 1
    fi
}

main() {
    log "=== 开始日程管理系统健康检查 ==="
    
    local service_ok=true
    local api_ok=true
    
    # 检查服务状态
    if ! check_service; then
        service_ok=false
        log "检测到服务未运行，尝试启动..."
        if ! restart_service; then
            log "服务启动失败，可能需要手动干预"
        fi
    fi
    
    # 检查API状态
    if ! check_api; then
        api_ok=false
        log "检测到API不可用，尝试重启服务..."
        if ! restart_service; then
            log "服务重启失败，可能需要手动干预"
        fi
        
        # 重启后再次检查API
        sleep 3
        if check_api; then
            log "API在重启后恢复正常"
            api_ok=true
        else
            log "API在重启后仍然异常"
        fi
    fi
    
    # 最终状态报告
    if $service_ok && $api_ok; then
        log "✅ 系统状态正常"
    else
        log "⚠️  系统存在异常，请检查日志"
    fi
    
    log "=== 健康检查完成 ==="
    echo ""
}

# 运行主函数
main 2>&1 | tee -a "$LOG_FILE"