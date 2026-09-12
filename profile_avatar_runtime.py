"""Optional per-user profile image storage."""
import base64
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

_DATA_URL=re.compile(r'^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$')


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS user_profile_images (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      data_url LONGTEXT NOT NULL,
      updated_at VARCHAR(40) NOT NULL
    );
    ''')


def validate(value):
    value=str(value or '')
    match=_DATA_URL.fullmatch(value)
    if not match:
        raise ValueError('Bitte ein PNG-, JPEG- oder WebP-Bild auswählen.')
    try:
        raw=base64.b64decode(match.group(2),validate=True)
    except Exception:
        raise ValueError('Das Profilbild konnte nicht gelesen werden.') from None
    if not raw or len(raw)>350_000:
        raise ValueError('Das Profilbild darf maximal 350 KB groß sein.')
    return value


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db

    previous_post=app.App.do_POST
    def do_POST(self):
        if urlparse(self.path).path!='/api/v1/profile/avatar':return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        action=str(body.get('action') or 'get')
        try:
            with app.db() as c:
                if action=='get':
                    row=c.execute('SELECT data_url,updated_at FROM user_profile_images WHERE user_id=?',(session['id'],)).fetchone()
                    return self.send_json(200,{'image':row['data_url'] if row else '', 'updated_at':row['updated_at'] if row else ''})
                if action=='remove':
                    c.execute('DELETE FROM user_profile_images WHERE user_id=?',(session['id'],))
                    return self.send_json(200,{'ok':True,'image':''})
                if action=='save':
                    image=validate(body.get('image'))
                    c.execute('DELETE FROM user_profile_images WHERE user_id=?',(session['id'],))
                    c.execute('INSERT INTO user_profile_images(user_id,data_url,updated_at) VALUES(?,?,?)',(session['id'],image,now_iso()))
                    return self.send_json(200,{'ok':True,'image':image})
                raise ValueError('Unbekannte Profilbild-Aktion.')
        except ValueError as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
