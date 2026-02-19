#!/usr/bin/env python3
"""
文件上传示例脚本
演示如何上传文件并通过API让AI读取
"""

import requests
import json
import base64
import os

# 配置
# 重要：在生产环境中，请通过环境变量设置认证信息，不要硬编码在源代码中
BASE_URL = os.getenv('CALENDAR_BASE_URL', 'http://localhost:8001')  # 日历服务地址
USERNAME = os.getenv('CALENDAR_USER', 'admin')  # 用户名
PASSWORD = os.getenv('CALENDAR_PASS', '[YOUR_SECURE_PASSWORD_HERE]')  # 密码，必须通过环境变量设置

def upload_file_via_multipart(file_path):
    """通过multipart/form-data上传文件"""
    url = f"{BASE_URL}/api/upload"
    files = {'file': open(file_path, 'rb')}
    
    response = requests.post(url, files=files, auth=(USERNAME, PASSWORD))
    return response.json()

def upload_file_via_base64(file_path):
    """通过base64上传文件"""
    url = f"{BASE_URL}/api/upload"
    
    with open(file_path, 'rb') as f:
        file_content = f.read()
    
    data = {
        'filename': os.path.basename(file_path),
        'content': base64.b64encode(file_content).decode('utf-8')
    }
    
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=data, auth=(USERNAME, PASSWORD))
    return response.json()

def get_file_list():
    """获取文件列表"""
    url = f"{BASE_URL}/api/uploads"
    response = requests.get(url, auth=(USERNAME, PASSWORD))
    return response.json()

def download_file(file_url):
    """下载文件"""
    url = f"{BASE_URL}{file_url}"
    response = requests.get(url, auth=(USERNAME, PASSWORD))
    return response.text

def main():
    print("=== 文件上传系统示例 ===\n")
    
    # 1. 创建测试文件
    test_content = """这是一个测试文件，用于演示文件上传功能。

文件内容包含：
1. 项目进度报告
2. 本周工作计划
3. 需要解决的问题列表

项目进度：
- 前端开发：完成90%
- 后端API：完成95%
- 测试：完成70%
- 部署：待开始

问题列表：
1. 数据库连接偶尔超时
2. 前端页面加载速度需要优化
3. 需要增加用户反馈功能

建议：
- 增加缓存机制
- 优化数据库查询
- 添加监控系统
"""
    
    test_file = "/tmp/test_project_report.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print(f"1. 创建测试文件: {test_file}")
    
    # 2. 上传文件
    print("\n2. 上传文件...")
    result = upload_file_via_multipart(test_file)
    
    if result.get('success'):
        file_info = result['data']
        print(f"   上传成功！文件名: {file_info['filename']}")
        print(f"   文件URL: {BASE_URL}{file_info['url']}")
        uploaded_filename = file_info['filename']
    else:
        print(f"   上传失败: {result.get('message')}")
        return
    
    # 3. 获取文件列表
    print("\n3. 获取文件列表...")
    files_result = get_file_list()
    
    if files_result.get('success'):
        files = files_result['data']
        print(f"   找到 {len(files)} 个文件:")
        for i, file in enumerate(files[:5], 1):  # 显示前5个文件
            print(f"   {i}. {file['name']} ({file['size']} bytes)")
        
        if len(files) > 5:
            print(f"   ... 和其他 {len(files) - 5} 个文件")
    else:
        print(f"   获取文件列表失败: {files_result.get('message')}")
    
    # 4. 读取文件内容（模拟AI分析）
    print("\n4. 读取并分析文件内容...")
    
    # 找到我们刚刚上传的文件
    target_file = None
    for file in files_result.get('data', []):
        if file['name'] == uploaded_filename:
            target_file = file
            break
    
    if target_file:
        content = download_file(target_file['url'])
        print(f"   文件内容预览:")
        print(f"   {'='*50}")
        print(content[:500] + "..." if len(content) > 500 else content)
        print(f"   {'='*50}")
        
        # 简单的分析示例
        lines = content.split('\n')
        print(f"   分析结果:")
        print(f"   - 文件大小: {len(content)} 字符")
        print(f"   - 行数: {len(lines)} 行")
        print(f"   - 包含'项目'关键词: {'项目' in content}")
        print(f"   - 包含'问题'关键词: {'问题' in content}")
    else:
        print("   未找到上传的文件")
    
    # 5. 清理
    print("\n5. 清理临时文件...")
    os.remove(test_file)
    print("   完成！")
    
    print("\n=== 使用说明 ===")
    print(f"1. 通过浏览器访问: {BASE_URL}/upload.html")
    print(f"2. 使用认证信息: {USERNAME} / [配置的密码]")
    print("3. 上传文件后，AI可以读取文件内容并进行分析")
    print("4. 支持的文件类型: 文本、图片、文档等（最大30MB）")
    print("\n注意：认证信息需要通过环境变量 CALENDAR_USER 和 CALENDAR_PASS 设置")

if __name__ == "__main__":
    main()