import http.server, json, pathlib, secrets, threading, webbrowser, sys

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, miner, port=8808):
        self.miner = miner
        self.token = secrets.token_hex(32)
        super().__init__(('127.0.0.1', port), Handler)
        self.allowed = {f'127.0.0.1:{self.server_port}', f'localhost:{self.server_port}'}

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def send(self, value, status=200, kind='application/json'):
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def host_ok(self):
        return self.headers.get('Host') in self.server.allowed

    def do_GET(self):
        if not self.host_ok():
            self.send({'error': 'Invalid host'}, 403)
            return
        if self.path == '/api/status':
            self.send(self.server.miner.snapshot())
            return
        if self.path == '/api/devices':
            self.send(self.server.miner.devices())
            return
        files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
        name = files.get(self.path)
        if not name:
            self.send({'error': 'Not found'}, 404)
            return
        root = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).parent)) / 'web'
        data = (root / name).read_bytes()
        if name == 'index.html':
            data = data.replace(b'PANEL_TOKEN', self.server.token.encode())
        self.send(data, kind={'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]])

    def do_POST(self):
        origins = {'http://' + x for x in self.server.allowed}
        if not self.host_ok() or self.headers.get('Origin') not in origins or (not secrets.compare_digest(self.headers.get('X-Panel-Token', ''), self.server.token)):
            self.send({'error': 'Forbidden'}, 403)
            return
        try:
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('JSON required')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            m = self.server.miner
            if not isinstance(data, dict):
                raise ValueError('Invalid request')
            if self.path == '/api/config':
                m.configure(data)
            elif self.path == '/api/start':
                m.start()
            elif self.path == '/api/stop':
                m.stop()
            elif self.path == '/api/unlock':
                m.unlock(key_hex=data.get('key') or None, wallet_file=data.get('file') or None, password=data.get('password') or None)
            elif self.path == '/api/lock':
                m.lock_wallet()
            elif self.path == '/api/tuning':
                m.apply_tuning()
            elif self.path == '/api/restore':
                m.hardware.restore()
            else:
                self.send({'error': 'Not found'}, 404)
                return
            self.send({'ok': True})
        except (ValueError, RuntimeError) as exc:
            self.send({'error': str(exc)}, 400)
        except Exception:
            self.send({'error': 'Local operation failed'}, 500)

def launch(miner, port=8808, open_browser=True):
    server = Server(miner, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(server.server_port) + '/'
    if open_browser:
        webbrowser.open(url)
    return (server, url)
