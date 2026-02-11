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

# 数据库路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'calendar.db')

# 上传目录
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 认证信息（与nginx保持一致）
AUTH_USER = 'admin'
AUTH_PASS = 'Admin@2026'
AUTH_STRING = base64.b64encode(f'{AUTH_USER}:{AUTH_PASS}'.encode()).decode()

class CalendarRequestHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    def check_auth(self):
        """检查HTTP Basic认证"""
        auth_header = self.headers.get('Authorization')
        if not auth_header:
            return False
        
        if not auth_header.startswith('Basic '):
            return False
        
        encoded = auth_header.split(' ')[1]
        decoded = base64.b64decode(encoded).decode()
        return decoded == f'{AUTH_USER}:{AUTH_PASS}'
    
    def require_auth(self):
        """要求认证"""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Restricted Access"')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'success': False,
            'message': '需要认证',
            'data': None
        }).encode())
        return False
    
    def send_json_response(self, data, status_code=200, message="成功", success=None):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
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
        if not self.check_auth():
            self.require_auth()
            return
        
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 路由分发
        if path == '/api/events' or path == '/api/events/':
            self.handle_get_events(parsed_path)
        elif path == '/api/events/today':
            self.handle_get_today_events()
        elif path == '/api/events/upcoming':
            self.handle_get_upcoming_events()
        elif path == '/api/uploads' or path == '/api/uploads/':
            self.handle_get_file_list()
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
    
    def do_POST(self):
        """处理POST请求"""
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
                    
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'type': file_type,
                        'url': f"/calendar/uploads/{filename}"
                    })
            
            # 按修改时间倒序排列（最新文件在前）
            files.sort(key=lambda x: x['modified'], reverse=True)
            
            self.send_json_response(files, message="获取文件列表成功")
            
        except Exception as e:
            self.send_error_response(f"获取文件列表失败：{str(e)}", 500)
    
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
            
            if file_size > 10 * 1024 * 1024:
                self.send_error_response("文件大小超过10MB限制", 400)
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
            if len(file_content) > 10 * 1024 * 1024:
                self.send_error_response("文件大小超过10MB限制", 400)
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