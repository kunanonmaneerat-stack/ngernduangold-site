import json
d = json.load(open('.system_control/content_manifest.json', encoding='utf-8'))
for dt in ['2026-07-16', '2026-07-17', '2026-07-20']:
    i = [x for x in d['items'] if x['date'] == dt][0]
    caps = i.get('captions', {})
    print(dt, 'caption keys:', sorted(caps.keys()))
    for k in ('youtube', 'facebook', 'threads'):
        v = caps.get(k)
        print('  ', k, '=', ('MISSING' if not v else repr(v[:40])))
