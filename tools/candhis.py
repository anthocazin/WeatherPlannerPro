#!/usr/bin/env python3
"""Candhis (Cerema) real-time wave buoys -> candhis.json for WeatherAssessment.html.

Runs only when the CANDHIS_KEY secret is set (API key given by the Candhis team,
candhis@cerema.fr). Uses getCampListeTR.php: last real-time value of every campaign,
one request per buoy type (0 = non-directional H1/3, 1 = directional Hm0, 2 = directional H1/3).
Data: Candhis – Cerema, Licence Ouverte Etalab (credit "Candhis" + date of the data).
"""
import json, os, sys, time, calendar, urllib.request

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
KEY = os.environ.get('CANDHIS_KEY', '').strip()
BASES = ['https://candhis.cerema.fr/API/v1/', 'https://candhis.cerema.fr/candhisPROD/API/v1/']

def call(base, fn, **q):
    url = base + fn + '?' + '&'.join('%s=%s' % kv for kv in q.items())
    req = urllib.request.Request(url, headers={'Authorization': KEY, 'User-Agent': 'WeatherAssessment buoy feed'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))

def num(v):
    try:
        x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return None if x >= 999 or x <= -999 else x

def utc(s):
    s = str(s).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d/%m/%Y %H:%M'):
        try: return calendar.timegm(time.strptime(s, fmt)) * 1000
        except ValueError: pass
    return None

def pick(row, head, *names):
    for n in names:
        for i, h in enumerate(head):
            if h.lower().startswith(n.lower()) and i < len(row): return num(row[i])
    return None

def main():
    os.makedirs(OUT, exist_ok=True)
    if not KEY:
        print('CANDHIS_KEY not set: Candhis skipped'); return
    rows, base_ok, errors = [], None, []
    for typ in (0, 1, 2):
        for base in ([base_ok] if base_ok else BASES):
            try:
                j = call(base, 'getCampListeTR.php', type=typ)
                base_ok = base; break
            except Exception as e:
                errors.append('%s type %d: %s' % (base, typ, e)); j = None
        if not j or not j.get('results'): continue
        head = [str(h) for h in j.get('entete', [])]
        for r in j['results']:
            t = utc(r[1]) if len(r) > 1 else None
            if not t: continue
            h13 = pick(r, head, 'H1/3'); hm0 = pick(r, head, 'Hm0')
            hs = h13 if h13 is not None else hm0
            if hs is None: continue
            rows.append({'code': str(r[0]), 't': t, 'type': typ, 'hs': hs, 'hlab': 'H1/3' if h13 is not None else 'Hm0',
                         'hmax': pick(r, head, 'Hmax'), 'per': pick(r, head, 'TH1/3', 'T02', 'T. au pic'),
                         'tp': pick(r, head, 'T. au pic'), 'dir': pick(r, head, 'Dir'), 'spread': pick(r, head, 'Etal'),
                         'sst': pick(r, head, 'Temp')})
        time.sleep(1)
    if errors: print('\n'.join(errors))
    with open(os.path.join(OUT, 'candhis.json'), 'w') as f:
        json.dump({'updated': int(time.time() * 1000), 'source': 'Candhis - Cerema (Licence Ouverte Etalab)', 'rows': rows}, f, separators=(',', ':'))
    print(len(rows), 'Candhis buoys')

if __name__ == '__main__':
    main()
