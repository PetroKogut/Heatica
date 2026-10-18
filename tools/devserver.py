"""Local server that mimics Cloudflare Workers static assets with
html_handling=auto-trailing-slash and not_found_handling=404-page.
Usage: python3 tools/devserver.py 8123"""
import http.server, os, sys, urllib.parse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8123

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(u.path)
        fs = ROOT / path.lstrip('/')
        if path.endswith('.html') and fs.is_file():
            return self._redirect(path[:-5] or '/', u.query)
        if path != '/' and path.endswith('/'):
            if (ROOT / (path.rstrip('/').lstrip('/') + '.html')).is_file() and not (fs / 'index.html').is_file():
                return self._redirect(path.rstrip('/'), u.query)
        # /foo -> foo.html wins over a directory of the same name without index.html (Workers behaviour)
        if (ROOT / (path.lstrip('/') + '.html')).is_file() and not (fs.is_dir() and (fs / 'index.html').is_file()):
            self.path = path + '.html' + ('?' + u.query if u.query else '')
            return super().do_GET()
        if not fs.exists() and not path.startswith('/cdn/'):
            self.send_response(404); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            nf = ROOT / '404.html'
            self.wfile.write(nf.read_bytes() if nf.exists() else b'404'); return
        return super().do_GET()
    def _redirect(self, loc, query):
        self.send_response(307); self.send_header('Location', loc + ('?' + query if query else '')); self.end_headers()
    def log_message(self, *a): pass

if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
