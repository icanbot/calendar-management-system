#!/usr/bin/env python3
"""
日程管理应用服务器
替代CGI方案，使用简单的HTTP服务器
"""
import os
import sys
import sqlite3
import json
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import base64
import traceback
import cgi
import shutil
import secrets
import time
from typing import Dict, Optional

# 数据库路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'calendar.db')

# 上传目录
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 认证信息（与nginx保持一致）
# 重要：在生产环境中，请通过环境变量设置这些值，不要硬编码在源代码中
# 例如：export CALENDAR_USER=your_username，export CALENDAR_PASS=your_password
AUTH_USER = os.getenv('CALENDAR_USER', 'admin')  # 默认用户名，建议通过环境变量覆盖
AUTH_PASS = os.getenv('CALENDAR_PASS', '[YOUR_SECURE_PASSWORD_HERE]')  # 必须通过环境变量设置密码
AUTH_STRING = base64.b64encode(f'{AUTH_USER}:{AUTH_PASS}'.encode()).decode()

# Session管理配置
SESSION_DB_PATH = os.path.join(DATA_DIR, 'sessions.db')
SESSION_TIMEOUT = 24 * 3600  # 24小时
SESSION_COOKIE_NAME = 'calendar_session'

# 内存中的session存储（简单实现）
_sessions: Dict[str, Dict] = {}

def init_session_db():
    """初始化session数据库（如果需要）"""
    if not os.path.exists(SESSION_DB_PATH):
        conn = sqlite3.connect(SESSION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE sessions (
                session_token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                user_agent TEXT,
                ip_address TEXT
            )
        ''')
        cursor.execute('CREATE INDEX idx_sessions_user_id ON sessions(user_id)')
        cursor.execute('CREATE INDEX idx_sessions_expires ON sessions(expires_at)')
        conn.commit()
        conn.close()

# 初始化session数据库
init_session_db()

class CalendarRequestHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    # ==================== Session管理方法 ====================
    
    def get_session_token(self) -> Optional[str]:
        """从Cookie或Authorization头获取session token"""
        # 首先检查Cookie
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookies = {}
            for cookie in cookie_header.split(';'):
                if '=' in cookie:
                    key, value = cookie.strip().split('=', 1)
                    cookies[key] = value
            if SESSION_COOKIE_NAME in cookies:
                return cookies[SESSION_COOKIE_NAME]
        
        # 检查Authorization头（用于API调用）
        auth_header = self.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header.split(' ')[1]
        
        return None
    
    def validate_session(self, session_token: str) -> bool:
        """验证session token是否有效"""
        if not session_token:
            return False
        
        try:
            conn = sqlite3.connect(SESSION_DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT session_token, expires_at 
                FROM sessions 
                WHERE session_token = ? AND (expires_at IS NULL OR expires_at > ?)
            ''', (session_token, datetime.now().isoformat()))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                # 更新最后活动时间
                conn = sqlite3.connect(SESSION_DB_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE sessions 
                    SET last_activity = ? 
                    WHERE session_token = ?
                ''', (datetime.now().isoformat(), session_token))
                conn.commit()
                conn.close()
                return True
            
            return False
        except sqlite3.Error:
            # 数据库错误，回退到内存存储
            return session_token in _sessions and _sessions[session_token].get('expires_at', 0) > time.time()
    
    def create_session(self, username: str, user_id: str = None) -> str:
        """创建新的session"""
        if user_id is None:
            user_id = username
        
        session_token = secrets.token_urlsafe(32)
        created_at = datetime.now()
        expires_at = created_at + timedelta(seconds=SESSION_TIMEOUT)
        
        try:
            conn = sqlite3.connect(SESSION_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions 
                (session_token, user_id, username, created_at, last_activity, expires_at, user_agent, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_token,
                user_id,
                username,
                created_at.isoformat(),
                created_at.isoformat(),
                expires_at.isoformat(),
                self.headers.get('User-Agent', ''),
                self.headers.get('X-Real-IP', self.client_address[0])
            ))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            # 回退到内存存储
            _sessions[session_token] = {
                'user_id': user_id,
                'username': username,
                'created_at': created_at,
                'expires_at': expires_at.timestamp(),
                'user_agent': self.headers.get('User-Agent', ''),
                'ip_address': self.client_address[0]
            }
        
        return session_token
    
    def delete_session(self, session_token: str):
        """删除session"""
        try:
            conn = sqlite3.connect(SESSION_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sessions WHERE session_token = ?', (session_token,))
            conn.commit()
            conn.close()
        except sqlite3.Error:
            # 回退到内存存储
            if session_token in _sessions:
                del _sessions[session_token]
    
    def get_current_user(self) -> Optional[Dict]:
        """获取当前登录用户信息"""
        session_token = self.get_session_token()
        if not session_token or not self.validate_session(session_token):
            return None
        
        try:
            conn = sqlite3.connect(SESSION_DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username 
                FROM sessions 
                WHERE session_token = ?
            ''', (session_token,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'user_id': result[0],
                    'username': result[1]
                }
        except sqlite3.Error:
            # 回退到内存存储
            if session_token in _sessions:
                return {
                    'user_id': _sessions[session_token]['user_id'],
                    'username': _sessions[session_token]['username']
                }
        
        return None
    
    def check_auth(self):
        """检查认证（兼容Basic Auth和Session）"""
        # 首先检查session
        if self.get_current_user() is not None:
            return True
        
        # 向后兼容：检查Basic Auth（主要用于Nginx传递的认证）
        auth_header = self.headers.get('Authorization')
        if auth_header and auth_header.startswith('Basic '):
            encoded = auth_header.split(' ')[1]
            try:
                decoded = base64.b64decode(encoded).decode()
                return decoded == f'{AUTH_USER}:{AUTH_PASS}'
            except:
                return False
        
        return False
    
    def require_auth(self):
        """要求认证"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # API请求返回JSON错误
        if path.startswith('/api/'):
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': False,
                'message': '需要登录',
                'data': None,
                'redirect': '/calendar/login.html'
            }).encode())
            return False
        else:
            # HTML页面重定向到登录页面
            self.send_response(302)
            self.send_header('Location', '/calendar/login.html')
            self.end_headers()
            return False
    
    def send_json_response(self, data, status_code=200, message="成功", success=None):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        
        if success is None:
            success = status_code in [200, 201]
        
        response = {
            "success": success,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
    
    def send_error_response(self, message, status_code=400):
        """发送错误响应"""
        self.send_json_response(None, status_code, message)
    
    def get_db_connection(self):
        """获取数据库连接"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row  # 返回字典格式
            return conn
        except sqlite3.Error as e:
            self.send_error_response(f"数据库连接失败：{str(e)}", 500)
            return None
    
    def parse_request_data(self):
        """解析请求数据"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            raw_data = self.rfile.read(content_length).decode('utf-8')
            try:
                return json.loads(raw_data)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def format_event(self, row):
        """格式化事件数据"""
        event = dict(row)
        
        # 处理参与者列表
        if event.get('participants'):
            event['participants'] = [p.strip() for p in event['participants'].split(',') if p.strip()]
        else:
            event['participants'] = []
        
        # 处理布尔值
        event['is_all_day'] = bool(event.get('is_all_day', 0))
        
        return event
    
    def validate_event_data(self, data, is_update=False):
        """验证事件数据"""
        errors = []
        
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
                    errors.append(f"{time_field} 时间格式无效")
        
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
            errors.append("事件类型无效")
        
        # 状态验证
        if data.get('status') and data['status'] not in ['scheduled', 'in_progress', 'completed', 'cancelled']:
            errors.append("状态无效")
        
        return errors
    
    def do_GET(self):
        """处理GET请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 特殊处理：登录页面和检查session的API不需要认证
        if path == '/login.html' or path == '/calendar/login.html':
            self.serve_static_file('login.html')
            return
        elif path == '/api/check_session' or path == '/api/check_session/':
            self.handle_check_session()
            return
        
        # 其他请求需要认证
        if not self.check_auth():
            self.require_auth()
            return
        
        # 路由分发
        if path == '/api/events' or path == '/api/events/':
            self.handle_get_events(parsed_path)
        elif path == '/api/events/today':
            self.handle_get_today_events()
        elif path == '/api/events/upcoming':
            self.handle_get_upcoming_events()
        elif path == '/api/uploads' or path == '/api/uploads/':
            self.handle_get_file_list()
        elif path == '/api/generated-files' or path == '/api/generated-files/':
            self.handle_get_generated_files()
        elif path.startswith('/api/events/'):
            try:
                event_id = int(path.split('/')[-1])
                self.handle_get_single_event(event_id)
            except ValueError:
                self.send_error_response("无效的事件ID", 400)
        elif path == '/':
            # 服务静态文件
            self.serve_static_file('index.html')
        elif os.path.exists(os.path.join(BASE_DIR, path.lstrip('/'))):
            self.serve_static_file(path.lstrip('/'))
        else:
            self.send_error_response("请求路径无效", 404)
    
    def do_OPTIONS(self):
        """处理OPTIONS请求，用于CORS预检"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Max-Age', '86400')  # 24小时
        self.end_headers()
    
    def do_POST(self):
        """处理POST请求"""
        # 特殊处理：登录API不需要认证
        if self.path == '/api/login' or self.path == '/api/login/':
            self.handle_login()
            return
        
        # 登出API需要认证
        if self.path == '/api/logout' or self.path == '/api/logout/':
            if not self.check_auth():
                self.require_auth()
                return
            self.handle_logout()
            return
        
        # 其他POST请求需要认证
        if not self.check_auth():
            self.require_auth()
            return
        
        if self.path == '/api/events' or self.path == '/api/events/':
            self.handle_create_event()
        elif self.path == '/api/upload' or self.path == '/api/upload/':
            self.handle_file_upload()
        elif self.path == '/api/upload_base64' or self.path == '/api/upload_base64/':
            self.handle_base64_upload()
        else:
            self.send_error_response("请求路径无效", 404)
    
    def do_PUT(self):
        """处理PUT请求"""
        if not self.check_auth():
            self.require_auth()
            return
        
        if self.path.startswith('/api/events/'):
            try:
                event_id = int(self.path.split('/')[-1])
                self.handle_update_event(event_id)
            except ValueError:
                self.send_error_response("无效的事件ID", 400)
        else:
            self.send_error_response("请求路径无效", 404)
    
    def do_DELETE(self):
        """处理DELETE请求"""
        if not self.check_auth():
            self.require_auth()
            return
        
        if self.path.startswith('/api/events/'):
            try:
                event_id = int(self.path.split('/')[-1])
                self.handle_delete_event(event_id)
            except ValueError:
                self.send_error_response("无效的事件ID", 400)
        elif self.path.startswith('/api/uploads/'):
            # 删除文件
            filename = self.path.split('/')[-1]
            if filename:
                self.handle_delete_file(filename)
            else:
                self.send_error_response("无效的文件名", 400)
        else:
            self.send_error_response("请求路径无效", 404)
    
    def serve_static_file(self, filename):
        """服务静态文件"""
        try:
            filepath = os.path.join(BASE_DIR, filename)
            
            if not os.path.exists(filepath):
                self.send_error_response("文件不存在", 404)
                return
            
            # 根据文件类型设置Content-Type
            if filename.endswith('.html'):
                content_type = 'text/html; charset=utf-8'
            elif filename.endswith('.css'):
                content_type = 'text/css'
            elif filename.endswith('.js'):
                content_type = 'application/javascript'
            elif filename.endswith('.png'):
                content_type = 'image/png'
            elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif filename.endswith('.xlsx') or filename.endswith('.xls'):
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif filename.endswith('.txt') or filename.endswith('.md') or filename.endswith('.log') or filename.endswith('.csv'):
                content_type = 'text/plain; charset=utf-8'
            else:
                content_type = 'application/octet-stream'  # 二进制流，适合未知文件类型
            
            with open(filepath, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            self.send_error_response(f"读取文件失败：{str(e)}", 500)
    
    # ==================== Session处理相关方法 ====================
    
    def handle_login(self):
        """处理登录请求"""
        try:
            data = self.parse_request_data()
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            # 验证用户名和密码
            if username == AUTH_USER and password == AUTH_PASS:
                # 创建session
                session_token = self.create_session(username)
                
                # 设置session cookie
                expires = datetime.now() + timedelta(seconds=SESSION_TIMEOUT)
                cookie = f'{SESSION_COOKIE_NAME}={session_token}; Path=/; HttpOnly; SameSite=Lax; Expires={expires.strftime("%a, %d %b %Y %H:%M:%S GMT")}'
                
                # 手动发送响应，以便设置cookie
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
                self.send_header('Set-Cookie', cookie)
                self.end_headers()
                
                response = {
                    "success": True,
                    "message": "登录成功",
                    "data": {
                        'session_token': session_token,
                        'username': username,
                        'expires_at': expires.isoformat()
                    },
                    "timestamp": datetime.now().isoformat()
                }
                self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
            else:
                self.send_error_response("用户名或密码错误", 401)
                
        except Exception as e:
            self.send_error_response(f"登录处理失败：{str(e)}", 500)
    
    def handle_logout(self):
        """处理登出请求"""
        session_token = self.get_session_token()
        
        # 清除cookie
        cookie = f'{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Expires=Thu, 01 Jan 1970 00:00:00 GMT'
        
        if session_token:
            self.delete_session(session_token)
        
        # 手动发送响应，以便设置cookie
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Set-Cookie', cookie)
        self.end_headers()
        
        response = {
            "success": True,
            "message": "已登出",
            "data": None,
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
    
    def handle_check_session(self):
        """检查session状态"""
        user = self.get_current_user()
        if user:
            self.send_json_response({
                'authenticated': True,
                'username': user['username'],
                'user_id': user['user_id']
            })
        else:
            self.send_json_response({
                'authenticated': False
            }, 401, "未登录")
    
    # ==================== 原有的事件处理方法 ====================
    
    def handle_get_events(self, parsed_path):
        """获取事件列表"""
        conn = self.get_db_connection()
        if not conn:
            return
        
        try:
            query_params = parse_qs(parsed_path.query)
            start_date = query_params.get('start', [None])[0]
            end_date = query_params.get('end', [None])[0]
            event_type = query_params.get('type', [None])[0]
            
            # 构建查询
            query = "SELECT * FROM events WHERE user_id = 1"
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
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            events = [self.format_event(row) for row in cursor.fetchall()]
            
            self.send_json_response(events)
            
        except Exception as e:
            self.send_error_response(f"查询事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_get_single_event(self, event_id):
        """获取单个事件"""
        conn = self.get_db_connection()
        if not conn:
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE id = ? AND user_id = 1", (event_id,))
            event = cursor.fetchone()
            
            if not event:
                self.send_error_response(f"事件ID {event_id} 不存在", 404)
                return
            
            self.send_json_response(self.format_event(event))
            
        except Exception as e:
            self.send_error_response(f"获取事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_create_event(self):
        """创建新事件"""
        conn = self.get_db_connection()
        if not conn:
            return
        
        try:
            event_data = self.parse_request_data()
            
            # 验证数据
            errors = self.validate_event_data(event_data)
            if errors:
                self.send_error_response("; ".join(errors), 400)
                return
            
            # 准备插入数据
            insert_data = {
                'user_id': 1,
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
            
            cursor = conn.cursor()
            cursor.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", values)
            event_id = cursor.lastrowid
            
            conn.commit()
            
            # 返回创建的事件
            cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            event = self.format_event(cursor.fetchone())
            
            self.send_json_response(event, 201, "事件创建成功")
            
        except Exception as e:
            conn.rollback()
            self.send_error_response(f"创建事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_update_event(self, event_id):
        """更新事件"""
        conn = self.get_db_connection()
        if not conn:
            return
        
        try:
            # 检查事件是否存在
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE id = ? AND user_id = 1", (event_id,))
            if not cursor.fetchone():
                self.send_error_response(f"事件ID {event_id} 不存在", 404)
                return
            
            event_data = self.parse_request_data()
            
            # 验证数据
            errors = self.validate_event_data(event_data, is_update=True)
            if errors:
                self.send_error_response("; ".join(errors), 400)
                return
            
            # 准备更新数据
            update_fields = []
            update_values = []
            
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
            updated_event = self.format_event(cursor.fetchone())
            
            self.send_json_response(updated_event, message="事件更新成功")
            
        except Exception as e:
            conn.rollback()
            self.send_error_response(f"更新事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_delete_event(self, event_id):
        """删除事件"""
        conn = self.get_db_connection()
        if not conn:
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM events WHERE id = ? AND user_id = 1", (event_id,))
            conn.commit()
            
            self.send_json_response(None, message="事件删除成功")
            
        except Exception as e:
            conn.rollback()
            self.send_error_response(f"删除事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_get_today_events(self):
        """获取今天的事件"""
        conn = self.get_db_connection()
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
            
            events = [self.format_event(row) for row in cursor.fetchall()]
            
            self.send_json_response(events, message="获取今日事件成功")
            
        except Exception as e:
            self.send_error_response(f"获取今日事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_get_upcoming_events(self):
        """获取即将发生的事件"""
        conn = self.get_db_connection()
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
            
            events = [self.format_event(row) for row in cursor.fetchall()]
            
            self.send_json_response(events, message="获取即将发生事件成功")
            
        except Exception as e:
            self.send_error_response(f"获取即将发生事件失败：{str(e)}", 500)
        finally:
            conn.close()
    
    def handle_get_file_list(self):
        """获取已上传文件列表"""
        try:
            if not os.path.exists(UPLOAD_DIR):
                self.send_json_response([])
                return
            
            files = []
            for filename in os.listdir(UPLOAD_DIR):
                filepath = os.path.join(UPLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    
                    # 确定文件类型
                    ext = filename.split('.')[-1].lower() if '.' in filename else ''
                    file_type = 'other'
                    if ext in ['txt', 'md', 'json', 'js', 'py', 'html', 'css', 'xml']:
                        file_type = 'text'
                    elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                        file_type = 'image'
                    elif ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
                        file_type = 'document'
                    
                    # 确定文件URL：优先使用/files/uploads/，如果不存在则使用/calendar/uploads/
                    files_uploads_path = f"/var/www/switchyomega/files/uploads/{filename}"
                    calendar_uploads_path = f"/calendar/uploads/{filename}"
                    files_uploads_url = f"/files/uploads/{filename}"
                    
                    url = files_uploads_url  # 默认使用/files/uploads/
                    
                    # 检查/files/uploads/中是否有符号链接或文件
                    if not os.path.exists(files_uploads_path):
                        # 如果/files/uploads/中不存在，创建符号链接
                        try:
                            source_path = os.path.join(UPLOAD_DIR, filename)
                            os.symlink(source_path, files_uploads_path)
                            print(f"已创建符号链接: {files_uploads_path} -> {source_path}")
                        except Exception as e:
                            # 如果创建符号链接失败，使用/calendar/uploads/路径
                            print(f"创建符号链接失败，使用备选路径: {e}")
                            url = calendar_uploads_path
                    
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'type': file_type,
                        'url': url
                    })
            
            # 按修改时间倒序排列（最新文件在前）
            files.sort(key=lambda x: x['modified'], reverse=True)
            
            self.send_json_response(files, message="获取文件列表成功")
            
        except Exception as e:
            self.send_error_response(f"获取文件列表失败：{str(e)}", 500)
    
    def handle_get_generated_files(self):
        """获取生成文件列表（来自/files/目录）"""
        try:
            # 生成文件目录路径
            GENERATED_DIR = '/var/www/switchyomega/files'
            
            if not os.path.exists(GENERATED_DIR):
                self.send_json_response([])
                return
            
            files = []
            for filename in os.listdir(GENERATED_DIR):
                filepath = os.path.join(GENERATED_DIR, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    
                    # 确定文件类型
                    ext = filename.split('.')[-1].lower() if '.' in filename else ''
                    file_type = 'other'
                    if ext in ['txt', 'md', 'json', 'js', 'py', 'html', 'css', 'xml']:
                        file_type = 'text'
                    elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                        file_type = 'image'
                    elif ext in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
                        file_type = 'document'
                    
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'type': file_type,
                        'url': f"/files/{filename}"  # 注意：这是nginx直接服务的路径
                    })
            
            # 按修改时间倒序排列（最新文件在前）
            files.sort(key=lambda x: x['modified'], reverse=True)
            
            self.send_json_response(files, message="获取生成文件列表成功")
            
        except Exception as e:
            self.send_error_response(f"获取生成文件列表失败：{str(e)}", 500)
    
    def handle_delete_file(self, filename):
        """删除文件"""
        try:
            # URL解码文件名（处理前端encodeURIComponent编码）
            import urllib.parse
            import posixpath
            
            # 解码URL编码
            decoded_filename = urllib.parse.unquote(filename)
            
            # 安全验证：防止路径遍历攻击
            safe_filename = posixpath.normpath(decoded_filename).lstrip('/')
            if safe_filename != decoded_filename or '..' in decoded_filename or decoded_filename.startswith('/'):
                self.send_error_response("无效的文件名", 400)
                return
            
            filepath = os.path.join(UPLOAD_DIR, safe_filename)
            
            if not os.path.exists(filepath):
                self.send_error_response("文件不存在", 404)
                return
            
            # 确保文件在上传目录内
            if not os.path.abspath(filepath).startswith(os.path.abspath(UPLOAD_DIR)):
                self.send_error_response("无效的文件路径", 403)
                return
            
            # 删除文件
            os.remove(filepath)
            
            self.send_json_response({
                'filename': decoded_filename,
                'deleted': True
            }, message="文件删除成功")
            
        except PermissionError:
            self.send_error_response("权限不足，无法删除文件", 403)
        except Exception as e:
            self.send_error_response(f"删除文件失败：{str(e)}", 500)
    
    def log_message(self, format, *args):
        """重写日志方法，减少输出"""
        pass
    
    def handle_file_upload(self):
        """处理文件上传（兼容multipart和base64）"""
        content_type = self.headers.get('Content-Type', '')
        
        if content_type.startswith('multipart/form-data'):
            self.handle_multipart_upload(content_type)
        elif content_type.startswith('application/json'):
            self.handle_base64_upload()
        else:
            self.send_error_response("不支持的Content-Type，请使用multipart/form-data或application/json", 400)
    
    def handle_multipart_upload(self, content_type):
        """处理multipart/form-data上传"""
        try:
            # 解析multipart数据
            environ = {
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
                'CONTENT_LENGTH': self.headers.get('Content-Length', 0)
            }
            
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ=environ
            )
            
            # 获取文件字段
            if 'file' not in form:
                self.send_error_response("没有提供文件字段'file'", 400)
                return
            
            file_item = form['file']
            
            # 处理多个文件的情况
            if isinstance(file_item, list):
                file_item = file_item[0]
            
            if not hasattr(file_item, 'filename'):
                self.send_error_response("无效的文件字段", 400)
                return
            
            filename = file_item.filename
            if not filename or filename.strip() == '':
                self.send_error_response("文件名不能为空", 400)
                return
            
            # 获取文件大小
            file_item.file.seek(0, 2)
            file_size = file_item.file.tell()
            file_item.file.seek(0)
            
            if file_size > 30 * 1024 * 1024:
                self.send_error_response("文件大小超过30MB限制", 400)
                return
            
            # 生成安全文件名
            original_filename = filename
            safe_filename = os.path.basename(original_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{safe_filename}"
            filepath = os.path.join(UPLOAD_DIR, safe_filename)
            
            # 保存文件
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(file_item.file, f)
            
            # 返回响应
            file_url = f"/uploads/{safe_filename}"
            file_info = {
                'success': True,
                'message': '文件上传成功',
                'filename': safe_filename,
                'original_filename': original_filename,
                'size': file_size,
                'url': file_url,
                'uploaded_at': datetime.now().isoformat()
            }
            
            self.send_json_response(file_info, 201)
            
        except Exception as e:
            self.send_error_response(f"multipart上传失败：{str(e)}", 500)
    
    def handle_base64_upload(self):
        """处理base64编码的文件上传"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if not content_length:
                self.send_error_response("请求体为空", 400)
                return
            
            raw_data = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(raw_data)
            
            if 'filename' not in data or 'content' not in data:
                self.send_error_response("缺少filename或content字段", 400)
                return
            
            # 解码base64内容
            file_content = base64.b64decode(data['content'])
            
            # 验证文件大小
            if len(file_content) > 30 * 1024 * 1024:
                self.send_error_response("文件大小超过30MB限制", 400)
                return
            
            # 生成安全文件名
            original_filename = data['filename']
            safe_filename = os.path.basename(original_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{safe_filename}"
            filepath = os.path.join(UPLOAD_DIR, safe_filename)
            
            # 保存文件
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            # 构建响应
            file_url = f"/uploads/{safe_filename}"
            file_info = {
                'success': True,
                'message': '文件上传成功（base64）',
                'filename': safe_filename,
                'original_filename': original_filename,
                'size': len(file_content),
                'url': file_url,
                'uploaded_at': datetime.now().isoformat()
            }
            
            self.send_json_response(file_info, 201)
            
        except json.JSONDecodeError:
            self.send_error_response("无效的JSON数据", 400)
        except Exception as e:
            self.send_error_response(f"base64上传失败：{str(e)}", 500)

def main():
    """主函数"""
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 启动服务器
    server_address = ('', 8001)
    httpd = HTTPServer(server_address, CalendarRequestHandler)
    
    print(f"日程管理服务器启动在 http://localhost:8001")
    print(f"访问地址: http://localhost:8001/")
    print(f"API地址: http://localhost:8001/api/events")
    print(f"认证用户: {AUTH_USER} / {AUTH_PASS}")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        httpd.server_close()

if __name__ == '__main__':
    main()