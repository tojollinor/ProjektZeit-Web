"""Versioned work schedules and a personal, non-payroll time comparison."""
import calendar
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import holidays
import admin_controls as acl
import system_features

TZ = ZoneInfo('Europe/Berlin')
STATES = {'BW':'Baden-Württemberg','BY':'Bayern','BE':'Berlin','BB':'Brandenburg','HB':'Bremen','HH':'Hamburg','HE':'Hessen','MV':'Mecklenburg-Vorpommern','NI':'Niedersachsen','NW':'Nordrhein-Westfalen','RP':'Rheinland-Pfalz','SL':'Saarland','SN':'Sachsen','ST':'Sachsen-Anhalt','SH':'Schleswig-Holstein','TH':'Thüringen'}
STATES.update({'BY-C':'Bayern – Ort mit Mariä Himmelfahrt', 'SN-C':'Sachsen – Ort mit Fronleichnam', 'TH-C':'Thüringen – Ort mit Fronleichnam', 'Augsburg':'Stadt Augsburg'})
PERMISSION = 'staff.models.manage'


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='seconds')


def midnight(day):
    return datetime.combine(day, time.min, TZ).astimezone(timezone.utc)


def days(start, end):
    while start < end:
        yield start
        start += timedelta(days=1)


def parse(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def day_value(value):
    result = date.fromisoformat(str(value))
    if not 2000 <= result.year <= 2099:
        raise ValueError('Bitte ein Datum zwischen 2000 und 2099 wählen.')
    return result


def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS work_models (
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      valid_from VARCHAR(10) NOT NULL, mode VARCHAR(12) NOT NULL,
      target_seconds INTEGER NOT NULL, weekdays_json VARCHAR(80) NOT NULL,
      subdivision VARCHAR(8) NOT NULL, version INTEGER NOT NULL DEFAULT 1,
      created_by INTEGER NOT NULL, created_at VARCHAR(40) NOT NULL,
      UNIQUE(user_id,valid_from));''')


def models(c, uid):
    result = []
    for row in c.execute('SELECT * FROM work_models WHERE user_id=? ORDER BY valid_from', (uid,)):
        item = dict(row)
        item['weekdays'] = json.loads(item.pop('weekdays_json'))
        result.append(item)
    return result


def model_on(items, day):
    return next((m for m in reversed(items) if m['valid_from'] <= str(day)), None)


def target(model, day):
    if model is None:
        return None
    weekdays = model['weekdays']
    if day.weekday() not in weekdays:
        return 0
    total = model['target_seconds']
    if model['mode'] == 'daily':
        return total
    if model['mode'] == 'weekly':
        count = len(weekdays)
        index = sorted(weekdays).index(day.weekday())
    else:
        month_days = [d for d in days(day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1]) + timedelta(days=1)) if d.weekday() in weekdays]
        count = len(month_days)
        index = month_days.index(day)
    # Exact allocation in integer seconds: no monthly/weekly rounding drift.
    return total * (index + 1) // count - total * index // count


@lru_cache(maxsize=256)
def holiday_calendar(year, subdivision):
    return holidays.country_holidays('DE', subdiv=subdivision.removesuffix('-C'), years=[year], language='de', categories=('public','catholic') if subdivision.endswith('-C') else ('public',))


def save(c, actor, body):
    acl.require_permission(c, actor, PERMISSION)
    uid = int(body.get('user_id') or 0)
    if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1', (uid,)).fetchone():
        raise ValueError('Aktiven Mitarbeiter auswählen.')
    valid = day_value(body.get('valid_from'))
    mode = body.get('mode')
    if mode not in ('daily','weekly','monthly'):
        raise ValueError('Täglich, wöchentlich oder monatlich auswählen.')
    try:
        value = Decimal(str(body.get('hours')).replace(',', '.')) * 3600
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError('Stunden müssen sekundengenau angegeben werden.')
        seconds = int(value)
    except (InvalidOperation, TypeError):
        raise ValueError('Ungültiger Stundenwert.')
    weekdays = body.get('weekdays')
    if not isinstance(weekdays, list) or not weekdays or len(weekdays) > 7 or any(type(x) is not int or not 0 <= x <= 6 for x in weekdays) or len(set(weekdays)) != len(weekdays):
        raise ValueError('Mindestens einen gültigen Arbeitstag auswählen.')
    weekdays = sorted(weekdays)
    limit = {'daily':86400, 'weekly':86400*len(weekdays), 'monthly':86400*4*len(weekdays)}[mode]
    if not 0 < seconds <= limit:
        raise ValueError('Sollstunden müssen positiv sein und dürfen 24 Stunden je Arbeitstag nicht überschreiten.')
    subdivision = str(body.get('subdivision') or '')
    if subdivision not in STATES:
        raise ValueError('Bundesland für Feiertage auswählen.')
    current = models(c, uid)
    ident = int(body.get('id') or 0)
    today = now().astimezone(TZ).date()
    if current and valid < today:
        raise ValueError('Weitere Änderungen dürfen frühestens ab heute gelten. Historische Modelle bleiben erhalten.')
    existing = next((m for m in current if m['id'] == ident), None) if ident else None
    if ident and (not existing or existing['valid_from'] < str(today)):
        raise ValueError('Nur heutige oder zukünftige Modelle können bearbeitet werden.')
    duplicate = next((m for m in current if m['valid_from'] == str(valid) and m['id'] != ident), None)
    if duplicate:
        raise ValueError('Für dieses Datum besteht bereits ein Modell. Dieses bitte bearbeiten.')
    if existing:
        if int(body.get('version') or 0) != existing['version']:
            raise ValueError('Modell wurde inzwischen geändert. Bitte neu laden.')
        updated = c.execute('''UPDATE work_models SET valid_from=?,mode=?,target_seconds=?,weekdays_json=?,subdivision=?,version=version+1
          WHERE id=? AND user_id=? AND version=?''', (str(valid), mode, seconds, json.dumps(weekdays), subdivision, ident, uid, existing['version']))
        if updated.rowcount != 1:
            raise ValueError('Modell wurde inzwischen geändert. Bitte neu laden.')
    else:
        ident = c.execute('''INSERT INTO work_models(user_id,valid_from,mode,target_seconds,weekdays_json,subdivision,created_by,created_at)
          VALUES(?,?,?,?,?,?,?,?)''', (uid,str(valid),mode,seconds,json.dumps(weekdays),subdivision,actor,iso(now()))).lastrowid
    system_features.audit(c, uid, actor, 'work_model', ident, 'Arbeitszeitmodell gespeichert', {'before':existing,'after':{'valid_from':str(valid),'mode':mode,'target_seconds':seconds,'weekdays':weekdays,'subdivision':subdivision}})
    return {'ok':True, 'id':ident}


def merge(spans):
    result = []
    for a,b in sorted(spans):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a,b])
    return result


def subtract(spans, pauses):
    for a,b in merge(pauses):
        result=[]
        for x,y in spans:
            if b <= x or a >= y:
                result.append([x,y])
            else:
                if x < a: result.append([x,a])
                if b < y: result.append([b,y])
        spans=result
    return spans


def summarize(rows):
    complete = [r for r in rows if r['closed']]
    configured = all(r['target_seconds'] is not None for r in rows)
    balance_known = all(r['difference_seconds'] is not None for r in complete)
    return {'target_seconds':sum(r['target_seconds'] for r in rows) if configured else None,
      'actual_seconds':sum(r['actual_seconds'] for r in rows),
      'holiday_seconds':sum(r['holiday_seconds'] for r in rows),
      'closed_difference_seconds':sum(r['difference_seconds'] for r in complete) if balance_known else None,
      'closed_days':len(complete), 'missing_model_days':sum(r['target_seconds'] is None for r in rows),
      'unclosed_work_days':sum(r['unclosed_work'] and r['closed'] for r in rows)}


def overview(c, uid, body, clock=None):
    clock = (clock or now()).astimezone(timezone.utc)
    today = clock.astimezone(TZ).date()
    selected = day_value(body.get('day') or today)
    month_start = selected.replace(day=1)
    month_end = selected.replace(day=calendar.monthrange(selected.year,selected.month)[1])+timedelta(days=1)
    week_start = selected - timedelta(days=selected.weekday())
    week_end = week_start + timedelta(days=7)
    start, end = min(month_start,week_start), max(month_end,week_end)
    items = models(c, uid)
    sessions = [dict(r) for r in c.execute('''SELECT id,started_at,ended_at FROM work_sessions
      WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?)''', (uid,iso(midnight(end)),iso(midnight(start))))]
    pauses = [dict(r) for r in c.execute('''SELECT work_session_id,started_at,ended_at FROM work_pauses
      WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?)''', (uid,iso(midnight(end)),iso(midnight(start))))]
    pause_map = {}
    for p in pauses:
        pause_map.setdefault(p['work_session_id'],[]).append((parse(p['started_at']),min(parse(p['ended_at']),clock) if p['ended_at'] else clock))
    net, gross, open_spans = [], [], []
    for s in sessions:
        a = parse(s['started_at'])
        b = min(parse(s['ended_at']),clock) if s['ended_at'] else clock
        if not s['ended_at']:
            open_spans.append((a,b))
        gross.append((a,b))
        net.extend(subtract([[a,b]],pause_map.get(s['id'],[])))
    net, gross = merge(net), merge(gross)
    def seconds(spans,a,b):
        return sum(max(0,int((min(y,b)-max(x,a)).total_seconds())) for x,y in spans)
    rows=[]
    for d in days(start,end):
        a,b = midnight(d),midnight(d+timedelta(days=1))
        model = model_on(items,d)
        plan = target(model,d)
        holiday = holiday_calendar(d.year,model['subdivision']).get(d,'') if model else ''
        actual = seconds(net,a,b)
        unclosed = seconds(open_spans,a,b)>0
        closed = d < today
        credit = (plan or 0) if holiday and closed else 0
        difference = actual+credit-plan if plan is not None and closed and not unclosed else None
        rows.append({'day':str(d),'target_seconds':plan,'actual_seconds':actual,
          'pause_seconds':max(0,seconds(gross,a,b)-actual),'holiday':holiday,'holiday_seconds':credit,
          'holiday_pending_seconds':(plan or 0) if holiday and not closed else 0,
          'difference_seconds':difference,'remaining_seconds':max(0,(plan or 0)-actual-(plan or 0 if holiday else 0)) if plan is not None else None,
          'closed':closed,'future':d>today,'unclosed_work':unclosed,'model_id':model['id'] if model else None})
    monthly=[r for r in rows if str(month_start)<=r['day']<str(month_end)]
    weekly=[r for r in rows if str(week_start)<=r['day']<str(week_end)]
    return {'selected_day':str(selected),'today':str(today),'as_of':iso(clock),'timezone':'Europe/Berlin',
      'day':next(r for r in rows if r['day']==str(selected)), 'week':summarize(weekly), 'month':summarize(monthly),
      'week_start':str(week_start),'week_end':str(week_end-timedelta(days=1)),
      'days':monthly,'models':items,'states':STATES,'can_manage':acl.can(c,uid,PERMISSION)}


def admin_list(c, uid, body):
    acl.require_permission(c,uid,PERMISSION)
    users=[dict(r) for r in c.execute('''SELECT u.id,u.username,u.active,COALESCE(p.first_name,'') first_name,COALESCE(p.last_name,'') last_name
      FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id ORDER BY u.username''')]
    all_models=[dict(r) for r in c.execute('SELECT * FROM work_models ORDER BY user_id,valid_from')]
    for m in all_models:m['weekdays']=json.loads(m.pop('weekdays_json'))
    return {'users':users,'models':all_models,'states':STATES,'today':str(now().astimezone(TZ).date())}


def install(app):
    acl.PERMISSION_CATEGORIES['Arbeitszeitmodelle']=[(PERMISSION,'Arbeitszeitmodelle der Mitarbeiter verwalten')]
    acl.ALL_PERMISSIONS.add(PERMISSION)
    acl.DEFAULT_ADMIN_PERMISSIONS.add(PERMISSION)
    import final_batch_runtime
    final_batch_runtime.DEPENDENCIES[PERMISSION]={'admin.options.view'}
    original_init=app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init
    previous=app.App.do_POST
    def post(self):
        path=urlparse(self.path).path
        handlers={'/api/v1/work-models/save':save,'/api/v1/work-models/admin':admin_list,'/api/v1/work-models/overview':overview}
        if path not in handlers:return previous(self)
        session=self.require(csrf=True)
        if not session:return
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('JSON-Objekt erforderlich.')
            with app.db() as c:result=handlers[path](c,session['id'],body)
            return self.send_json(200,result)
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,KeyError,TypeError,OverflowError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=post
