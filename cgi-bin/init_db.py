#!/usr/bin/env python3
"""
日程管理数据库初始化脚本
"""
import os
import sqlite3
import sys

# 数据库路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'calendar.db')

def init_database():
    """初始化数据库表结构"""
    
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 创建用户表（简化版，当前只支持单用户）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 插入默认用户（如果不存在）
    cursor.execute('''
    INSERT OR IGNORE INTO users (username, email) 
    VALUES (?, ?)
    ''', ('admin', 'shangbh@outlook.com'))
    
    # 创建事件表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        event_type TEXT NOT NULL CHECK(event_type IN ('meeting', 'work', 'personal', 'other')),
        start_time TIMESTAMP NOT NULL,
        end_time TIMESTAMP NOT NULL,
        location TEXT,
        participants TEXT,  -- 逗号分隔的参与者列表
        status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'in_progress', 'completed', 'cancelled')),
        reminder_minutes INTEGER DEFAULT 15,  -- 提前提醒分钟数
        is_all_day BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_time ON events(start_time, end_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)')
    
    # 创建项目表（可选，用于关联工作安排）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # 事件-项目关联表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_projects (
        event_id INTEGER NOT NULL,
        project_id INTEGER NOT NULL,
        PRIMARY KEY (event_id, project_id),
        FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )
    ''')
    
    # 提交更改
    conn.commit()
    
    # 验证表结构
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"已创建的表：{', '.join([t[0] for t in tables])}")
    
    # 统计记录
    cursor.execute("SELECT COUNT(*) FROM events")
    event_count = cursor.fetchone()[0]
    print(f"当前事件数量：{event_count}")
    
    cursor.execute("SELECT COUNT(*) FROM projects")
    project_count = cursor.fetchone()[0]
    print(f"当前项目数量：{project_count}")
    
    conn.close()
    return True

if __name__ == '__main__':
    print("正在初始化日程管理数据库...")
    try:
        success = init_database()
        if success:
            print(f"数据库初始化成功！数据库位置：{DB_PATH}")
            print("表结构已就绪，可以开始使用日程管理功能。")
        else:
            print("数据库初始化失败。")
            sys.exit(1)
    except Exception as e:
        print(f"初始化过程中出现错误：{str(e)}")
        sys.exit(1)