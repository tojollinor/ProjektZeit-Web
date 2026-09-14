"""Project collaboration does not transfer ownership of employees' recorded work."""
import admin_controls

def get(c,uid,pid,accounting=False):
    p=c.execute('SELECT * FROM projects WHERE id=? AND is_system=0',(int(pid),)).fetchone()
    if not p:raise ValueError('Projekt nicht gefunden.')
    p=dict(p)
    if uid not in (p['owner_id'],p.get('assigned_user_id')) and not (accounting and admin_controls.can(c,uid,'bookkeeping.view')):raise PermissionError('Projekt nicht zugänglich.')
    return p

def can_work(c,uid,pid):
    try:return bool(get(c,uid,pid)['active'])
    except (ValueError,PermissionError):return False
