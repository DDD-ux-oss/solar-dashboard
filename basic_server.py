# 最基本的HTTP服务器脚本
# 只使用Python内置模块

import http.server
import socketserver

# 设置端口
PORT = 3000

# 使用SimpleHTTPRequestHandler处理请求
handler = http.server.SimpleHTTPRequestHandler

# 创建并启动服务器
with socketserver.TCPServer(('', PORT), handler) as httpd:
    print(f"\n新鼎能源项目日报系统服务已启动")
    print(f"请在浏览器中访问: http://localhost:{PORT}")
    print("\n按 Ctrl+C 停止服务器\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")