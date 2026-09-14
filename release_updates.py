"""Bounded, shared checks against successfully published main builds."""
import json
import os
import re
import threading
import time
from urllib.request import Request, urlopen

VERSION = '0.7.3'
REPOSITORY = 'tojollinor/ProjektZeit-Web'
API = 'https://api.github.com/repos/' + REPOSITORY
_lock = threading.Lock()
_cache = None
_expires = 0


def revision():
    value = os.environ.get('BUILD_REVISION', '')
    return value if re.fullmatch(r'[0-9a-f]{40}', value) else ''


def _read(path):
    request = Request(API + path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'ProjektZeit-Update', 'X-GitHub-Api-Version': '2022-11-28'})
    with urlopen(request, timeout=3) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Update-Antwort zu groß')
    return json.loads(raw)


def check():
    global _cache, _expires
    current = revision()
    base = {'version': VERSION, 'revision': current}
    if not current:
        return dict(base, state='unknown', message='Dieser Build hat keine GitHub-Buildkennung. Ein Versionsvergleich ist nicht möglich.')
    if _cache and time.monotonic() < _expires:
        return _cache.copy()
    if not _lock.acquire(blocking=False):
        return dict(base, state='checking', message='Die Aktualisierungsprüfung läuft bereits. Bitte kurz darauf erneut prüfen.')
    try:
        if _cache and time.monotonic() < _expires:
            cached = _cache.copy()
            _lock.release()
            return cached
        runs = _read('/actions/workflows/docker-publish.yml/runs?branch=main&event=push&status=success&per_page=10').get('workflow_runs', [])
        published = next((r for r in runs if r.get('conclusion') == 'success' and r.get('head_branch') == 'main' and r.get('event') == 'push'), None)
        if not published or not re.fullmatch(r'[0-9a-f]{40}', published.get('head_sha', '')):
            raise ValueError('Kein erfolgreicher Main-Publish gefunden')
        latest = published['head_sha']
        relation = 'identical' if latest == current else _read('/compare/' + current + '...' + latest).get('status')
        if relation not in ('identical', 'ahead', 'behind'):
            raise ValueError('Builds können nicht eindeutig verglichen werden')
        available = relation == 'ahead'
        result = dict(base, state='available' if available else 'current', latest_revision=latest,
                      message='Ein erfolgreich veröffentlichtes Update steht bereit.' if available else 'Kein neuerer erfolgreich veröffentlichter Main-Build verfügbar.',
                      workflow_url='https://github.com/' + REPOSITORY + '/actions/runs/' + str(int(published['id'])))
        ttl = 300
    except Exception:
        result = dict(base, state='error', message='GitHub konnte nicht zuverlässig geprüft werden. Bitte später erneut versuchen; der aktuelle Stand ist unbekannt.')
        ttl = 30
    # Publish the result before allowing another thread to start a check.
    _cache, _expires = result, time.monotonic() + ttl
    _lock.release()
    return result.copy()
