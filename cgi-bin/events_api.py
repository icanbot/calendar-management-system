#!/usr/bin/env python3
"""
日程事件API接口
支持CRUD操作：创建、读取、更新、删除事件
"""
import os
import sys
import sqlite3
import json
import cgi
import cgitb
from datetime import datetime, timedelta
import urllib.parse

# 启用CGI错误跟踪（开发阶段）
cgitb.enable()

# 数据库路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'calendar.db')

# 响应头
def print_json_response(data, status_code=200, message="成功"):
    """输出JSON格式响应"""
    print("Content-Type: application/json; charset=utf-8")
    print(f"Status: {status_code}")
    print()
    response = {
        "success": status_code == 200,
        "message": message,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    print(json.dumps(response, ensure_ascii=False, indent=2))

def print_error(message, status_code=400):
    """输出错误响应"""
    print_json_response(None, status_code, message)

def get_db_connection():
    """获取数据库连接"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 返回字典格式
        return conn
    except sqlite3.Error as e:
        print_error(f"数据库连接失败：{str(e)}", 500)
        return None

def parse_request():
    """解析HTTP请求，获取方法和参数"""
    
    # 获取请求方法
    method = os.environ.get('REQUEST_METHOD', 'GET')
    
    # 获取查询参数
    query_string = os.environ.get('QUERY_STRING', '')
    query_params = urllib.parse.parse_qs(query_string)
    
    # 获取路径信息
    path_info = os.environ.get('PATH_INFO', '')
    
    # 解析JSON请求体（对于POST/PUT）
    post_data = {}
    if method in ['POST', 'PUT']:
        form = cgi.FieldStorage()
        if 'application/json' in os.environ.get('CONTENT_TYPE', ''):
            # JSON格式请求
            try:
                content_length = int(os.environ.get('CONTENT_LENGTH', 0))
                if content_length:
                    post_data = json.loads(sys.stdin.read(content_length))
            except Exception as e:
                pass
        else:
            # 表单格式请求
            for key in form:
                if form[key].filename:
                    # 文件上传（不支持）
                    continue
                if isinstance(form[key], list):
                    post_data[key] = [item.value for item in form[key]]
                else:
                    post_data[key] = form[key].value
    
    return {
        'method': method,
        'path': path_info,
        'query': query_params,
        'data': post_data
    }

def validate_event_data(data, is_update=False):
    """验证事件数据"""
    errors = []
    
    # 必需字段检查
    if not is_update:
        if not data.get('title'):
            errors.append("标题不能为空")
        if not data.get('start_time'):
            errors.append("开始时间不能为空")
        if not data.get('end_time'):
            errors.append("结束时间不能为空")
    
    # 时间格式验证
    for time_field in ['start_time', 'end_time']:
        if data.get(time_field):
            try:
                datetime.fromisoformat(data[time_field].replace('Z', '+00:00'))
            except ValueError:
                errors.append(f"{time_field} 时间格式无效，请使用ISO格式")
    
    # 时间逻辑验证
    if data.get('start_time') and data.get('end_time'):
        try:
            start = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            if start >= end:
                errors.append("开始时间必须早于结束时间")
        except ValueError:
            pass
    
    # 事件类型验证
    if data.get('event_type') and data['event_type'] not in ['meeting', 'work', 'personal', 'other']:
        errors.append("事件类型无效，可选值：meeting, work, personal, other")
    
    # 状态验证
    if data.get('status') and data['status'] not in ['scheduled', 'in_progress', 'completed', 'cancelled']:
        errors.append("状态无效，可选值：scheduled, in_progress, completed, cancelled")
    
    return errors

def format_event(row):
    """格式化事件数据为字典"""
    event = dict(row)
    
    # 转换时间格式
    for time_field in ['start_time', 'end_time', 'created_at', 'updated_at']:
        if event.get(time_field):
            event[time_field] = event[time_field]
    
    # 处理参与者列表
    if event.get('participants'):
        event['participants'] = [p.strip() for p in event['participants'].split(',') if p.strip()]
    else:
        event['participants'] = []
    
    # 处理布尔值
    event['is_all_day'] = bool(event.get('is_all_day', 0))
    
    return event

# API路由处理
def handle_events(request):
    """处理事件集合请求"""
    
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    if request['method'] == 'GET':
        # 获取事件列表
        try:
            # 获取查询参数
            start_date = request['query'].get('start', [None])[0]
            end_date = request['query'].get('end', [None])[0]
            event_type = request['query'].get('type', [None])[0]
            
            # 构建查询
            query = "SELECT * FROM events WHERE user_id = 1"  # 当前只支持单用户
            params = []
            
            if start_date:
                query += " AND start_time >= ?"
                params.append(start_date)
            if end_date:
                query += " AND end_time <= ?"
                params.append(end_date)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            
            query += " ORDER BY start_time ASC"
            
            cursor.execute(query, params)
            events = [format_event(row) for row in cursor.fetchall()]
            
            print_json_response(events)
            
        except Exception as e:
            print_error(f"查询事件失败：{str(e)}", 500)
    
    elif request['method'] == 'POST':
        # 创建新事件
        try:
            event_data = request['data']
            
            # 验证数据
            errors = validate_event_data(event_data)
            if errors:
                print_error("; ".join(errors), 400)
                return
            
            # 准备插入数据
            insert_data = {
                'user_id': 1,  # 默认用户
                'title': event_data.get('title', ''),
                'description': event_data.get('description', ''),
                'event_type': event_data.get('event_type', 'work'),
                'start_time': event_data.get('start_time'),
                'end_time': event_data.get('end_time'),
                'location': event_data.get('location', ''),
                'participants': ', '.join(event_data.get('participants', [])) if isinstance(event_data.get('participants'), list) else event_data.get('participants', ''),
                'status': event_data.get('status', 'scheduled'),
                'reminder_minutes': event_data.get('reminder_minutes', 15),
                'is_all_day': 1 if event_data.get('is_all_day') else 0,
                'updated_at': datetime.now().isoformat()
            }
            
            # 执行插入
            columns = ', '.join(insert_data.keys())
            placeholders = ', '.join(['?'] * len(insert_data))
            values = list(insert_data.values())
            
            cursor.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", values)
            event_id = cursor.lastrowid
            
            conn.commit()
            
            # 返回创建的事件
            cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            event = format_event(cursor.fetchone())
            
            print_json_response(event, 201, "事件创建成功")
            
        except Exception as e:
            conn.rollback()
            print_error(f"创建事件失败：{str(e)}", 500)
    
    else:
        print_error(f"不支持的请求方法：{request['method']}", 405)
    
    conn.close()

def handle_single_event(request, event_id):
    """处理单个事件请求"""
    
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    # 检查事件是否存在
    cursor.execute("SELECT * FROM events WHERE id = ? AND user_id = 1", (event_id,))
    event = cursor.fetchone()
    
    if not event:
        print_error(f"事件ID {event_id} 不存在", 404)
        conn.close()
        return
    
    if request['method'] == 'GET':
        # 获取单个事件详情
        print_json_response(format_event(event))
    
    elif request['method'] == 'PUT':
        # 更新事件
        try:
            event_data = request['data']
            
            # 验证数据
            errors = validate_event_data(event_data, is_update=True)
            if errors:
                print_error("; ".join(errors), 400)
                return
            
            # 准备更新数据
            update_fields = []
            update_values = []
            
            # 允许更新的字段
            allowed_fields = ['title', 'description', 'event_type', 'start_time', 'end_time', 
                             'location', 'participants', 'status', 'reminder_minutes', 'is_all_day']
            
            for field in allowed_fields:
                if field in event_data:
                    if field == 'participants' and isinstance(event_data[field], list):
                        update_fields.append(f"{field} = ?")
                        update_values.append(', '.join(event_data[field]))
                    elif field == 'is_all_day':
                        update_fields.append(f"{field} = ?")
                        update_values.append(1 if event_data[field] else 0)
                    else:
                        update_fields.append(f"{field} = ?")
                        update_values.append(event_data[field])
            
            # 添加更新时间
            update_fields.append("updated_at = ?")
            update_values.append(datetime.now().isoformat())
            
            # 执行更新
            update_values.append(event_id)
            update_query = f"UPDATE events SET {', '.join(update_fields)} WHERE id = ? AND user_id = 1"
            
            cursor.execute(update_query, update_values)
            conn.commit()
            
            # 返回更新后的事件
            cursor.execute("SELECT * FROM events WHERE id = ? AND user_id = 1", (event_id,))
            updated_event = format_event(cursor.fetchone())
            
            print_json_response(updated_event, message="事件更新成功")
            
        except Exception as e:
            conn.rollback()
            print_error(f"更新事件失败：{str(e)}", 500)
    
    elif request['method'] == 'DELETE':
        # 删除事件
        try:
            cursor.execute("DELETE FROM events WHERE id = ? AND user_id = 1", (event_id,))
            conn.commit()
            
            print_json_response(None, message="事件删除成功")
            
        except Exception as e:
            conn.rollback()
            print_error(f"删除事件失败：{str(e)}", 500)
    
    else:
        print_error(f"不支持的请求方法：{request['method']}", 405)
    
    conn.close()

def handle_today_events(request):
    """获取今天的事件"""
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        today = datetime.now().date().isoformat()
        tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM events 
            WHERE user_id = 1 
            AND start_time >= ? 
            AND start_time < ?
            ORDER BY start_time ASC
        ''', (today, tomorrow))
        
        events = [format_event(row) for row in cursor.fetchall()]
        
        print_json_response(events, message="获取今日事件成功")
        
    except Exception as e:
        print_error(f"获取今日事件失败：{str(e)}", 500)
    
    conn.close()

def handle_upcoming_events(request):
    """获取即将发生的事件（未来7天）"""
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        now = datetime.now().isoformat()
        next_week = (datetime.now() + timedelta(days=7)).isoformat()
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM events 
            WHERE user_id = 1 
            AND start_time >= ? 
            AND start_time < ?
            AND status = 'scheduled'
            ORDER BY start_time ASC
        ''', (now, next_week))
        
        events = [format_event(row) for row in cursor.fetchall()]
        
        print_json_response(events, message="获取即将发生事件成功")
        
    except Exception as e:
        print_error(f"获取即将发生事件失败：{str(e)}", 500)
    
    conn.close()

# 主处理函数
def main():
    """主请求处理函数"""
    try:
        # 解析请求
        request = parse_request()
        path = request['path']
        
        # 路由分发
        if path == '' or path == '/':
            handle_events(request)
        elif path == '/today':
            handle_today_events(request)
        elif path == '/upcoming':
            handle_upcoming_events(request)
        elif path.startswith('/'):
            # 处理单个事件：/123
            try:
                event_id = int(path.lstrip('/').split('/')[0])
                handle_single_event(request, event_id)
            except ValueError:
                print_error("无效的事件ID", 400)
        else:
            print_error("请求路径无效", 404)
            
    except Exception as e:
        print_error(f"服务器内部错误：{str(e)}", 500)

if __name__ == '__main__':
    main()