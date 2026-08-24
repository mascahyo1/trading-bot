#!/usr/bin/env python3
"""
Simple HTTP/HTTPS proxy server untuk routing browser traffic.
Jalankan di VPS, browser pakai proxy ini.
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import threading
import sys

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            url = self.path
            req = urllib.request.Request(url, headers={k: v for k, v in self.headers.items()})
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_POST(self):
        self.do_GET()

    def do_CONNECT(self):
        # HTTPS tunneling
        try:
            host, port = self.path.split(':')
            port = int(port)
            with socket.create_connection((host, port), timeout=30) as sock:
                self.send_response(200)
                self.end_headers()
                # Bidirectional tunnel
                def forward(src, dst):
                    try:
                        while True:
                            data = src.recv(4096)
                            if not data:
                                break
                            dst.sendall(data)
                    except:
                        pass
                t1 = threading.Thread(target=forward, args=(self.connection, sock))
                t2 = threading.Thread(target=forward, args=(sock, self.connection))
                t1.start()
                t2.start()
                t1.join()
                t2.join()
        except Exception as e:
            self.send_response(502)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    with socketserver.ThreadingTCPServer(('127.0.0.1', port), ProxyHandler) as httpd:
        print(f'Proxy running on 127.0.0.1:{port}')
        httpd.serve_forever()
