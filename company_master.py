"""Company master data and defaults for newly configured employees."""
import admin_controls as acl
import system_features

FIELDS = ('name', 'name_addition', 'street', 'house_number', 'zip_code', 'city',
          'country', 'email', 'phone', 'website', 'tax_number', 'vat_id', 'subdivision')


def read(c):
    stored = acl.setting(c, 'company.master', {})
    return {**{key: 'Deutschland' if key == 'country' else '' for key in FIELDS},
            'version': 0, **stored}


def default_region(c):
    return read(c)['subdivision']


def save(c, uid, body):
    import work_models
    acl.require_permission(c, uid, 'system.options.edit')
    old = read(c)
    if int(body.get('version', -1)) != old['version']:
        raise ValueError('Unternehmensdaten wurden inzwischen geändert. Bitte neu laden.')
    data = {key: str(body.get(key, old[key]) or '').strip()[:250] for key in FIELDS}
    if not data['name']:
        raise ValueError('Bitte einen Unternehmensnamen eingeben.')
    if data['subdivision'] not in work_models.STATES:
        raise ValueError('Bitte eine gültige Standard-Feiertagsregion auswählen.')
    if data['email'] and ('@' not in data['email'] or any(ch.isspace() for ch in data['email'])):
        raise ValueError('Bitte eine gültige E-Mail-Adresse eingeben.')
    data['version'] = old['version'] + 1
    acl.set_setting(c, 'company.master', data)
    system_features.audit(c, uid, uid, 'company', 1, 'Unternehmensstammdaten geändert', {'old': old, 'new': data})
    return {'company': data}
