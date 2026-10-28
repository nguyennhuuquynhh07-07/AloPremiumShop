import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Locket Gold is running 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Không in access log rác ra console
        return

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"🌐 Health-check server listening on port {port}")
    httpd.serve_forever()

def keep_alive():
    """Khởi chạy web server ngầm để các nền tảng đám mây (Render, Koyeb) ping kiểm tra sống."""
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

