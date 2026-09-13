"""Bounded, recursively sanitized diagnostic data; never export raw secrets."""
import re

SENSITIVE = re.compile(r'password|passwd|secret|token|authorization|cookie|api.?key|oauth.?code', re.I)
ASSIGNMENT = re.compile(r'(?i)((?:password|passwd|client_secret|access_token|refresh_token|api_key|authorization|code)\s*[=:]\s*)[^\s&,;]+')
BEARER = re.compile(r'(?i)Bearer\s+[^\s,;]+')

def sanitize(value, depth=0):
    if depth > 8:
        return '[begrenzt]'
    if isinstance(value, dict):
        return {str(k): '[entfernt]' if SENSITIVE.search(str(k)) else sanitize(v, depth+1) for k,v in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, depth+1) for v in value[:1000]]
    if isinstance(value, str):
        return ASSIGNMENT.sub(r'\1[entfernt]', BEARER.sub('Bearer [entfernt]', value))[:2000]
    return value
