"""Automatic frontend version detection and cache-safe index delivery."""
import hashlib
import re
from urllib.parse import urlparse


ASSET_SUFFIXES = ('.html', '.js', '.css')


def _frontend_version(static_dir):
    digest = hashlib.sha256()
    for path in sorted(p for p in static_dir.rglob('*') if p.is_file() and p.suffix.lower() in ASSET_SUFFIXES):
        digest.update(path.relative_to(static_dir).as_posix().encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()[:20]


def _versioned_index(static_dir, version):
    html = (static_dir / 'index.html').read_text(encoding='utf-8')
    meta = f'<meta name="pz-frontend-version" content="{version}">'
    if 'name="pz-frontend-version"' not in html:
        html = html.replace('</head>', f'  {meta}\n</head>', 1)

    pattern = re.compile(r'''\b(src|href)=(?P<q>["'])(?P<url>/[^"']+\.(?:js|css)(?:\?[^"']*)?)(?P=q)''')
    def rewrite(match):
        url = match.group('url')
        if 'pzv=' in url:
            return match.group(0)
        separator = '&' if '?' in url else '?'
        quote = match.group('q')
        return f'{match.group(1)}={quote}{url}{separator}pzv={version}{quote}'
    return pattern.sub(rewrite, html)


def install(app):
    version = _frontend_version(app.STATIC)
    index_html = _versioned_index(app.STATIC, version).encode('utf-8')
    app.FRONTEND_VERSION = version

    previous_get = app.App.do_GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/v1/frontend/version':
            return self.send_json(200, {'version': version})
        if path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(index_html)))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('X-PZ-Frontend-Version', version)
            self.end_headers()
            self.wfile.write(index_html)
            return
        return previous_get(self)
    app.App.do_GET = do_GET
