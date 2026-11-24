#!/usr/bin/env python3
"""Candhis (Cerema) real-time wave buoys -> candhis.json for WeatherAssessment.html.

Runs only when the CANDHIS_KEY secret is set (key given by the Candhis team, candhis@cerema.fr).
Uses getCampListeTR.php (latest real-time value of every campaign of a buoy type):
  type 1 = directional Hm0, type 2 = directional H1/3 -> every 30 min
  type 0 = non-directional H1/3                         -> every 3 h
Quota: 150 requests per day. This script uses about 104 per day and never more than
DAILY_CAP per UTC day (counter kept in candhis.json on the buoy-data branch); on HTTP 429
(daily quota reached) or 423 it stops and keeps the previous values.
Data: Candhis - Cerema, Licence Ouverte Etalab (credit "Candhis" + date of the data).
"""
import json, os, sys, time, calendar, urllib.request, urllib.error

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
KEY = os.environ.get('CANDHIS_KEY', '').strip().strip('"\'').strip()
REPO = os.environ.get('GITHUB_REPOSITORY', 'anthocazin/weatherplannerpro')
BASES = ['https://candhis.cerema.fr/API/v1/', 'https://candhis.cerema.fr/candhisPROD/API/v1/']
EVERY = {1: 30, 2: 30, 0: 180}   # minutes between two requests of the same type
DAILY_CAP = 130                  # keeps a margin under the 150/day quota for manual tests

AUTHS = ['{k}', 'Bearer {k}']

def call(base, fn, auth='{k}', **q):
    url = base + fn + '?' + '&'.join('%s=%s' % kv for kv in q.items())
    req = urllib.request.Request(url, headers={'Authorization': auth.format(k=KEY), 'User-Agent': 'WeatherAssessment buoy feed (github.com/%s)' % REPO})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))

def num(v):
    try: x = float(str(v).replace(',', '.'))
    except (TypeError, ValueError): return None
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

def parse(j, typ):
    head = [str(h) for h in (j.get('entete') or [])]; out = []
    for r in j.get('results') or []:
        t = utc(r[1]) if len(r) > 1 else None
        if not t: continue
        h13 = pick(r, head, 'H1/3'); hm0 = pick(r, head, 'Hm0'); hs = h13 if h13 is not None else hm0
        if hs is None: continue
        out.append({'code': str(r[0]), 't': t, 'type': typ, 'hs': hs, 'hlab': 'H1/3' if h13 is not None else 'Hm0',
                    'hmax': pick(r, head, 'Hmax'), 'per': pick(r, head, 'TH1/3', 'T02'), 'tp': pick(r, head, 'T. au pic'),
                    'dir': pick(r, head, 'Dir'), 'spread': pick(r, head, 'Etal'), 'sst': pick(r, head, 'Temp')})
    return out

def previous():
    try:
        req = urllib.request.Request('https://raw.githubusercontent.com/%s/buoy-data/candhis.json?t=%d' % (REPO, time.time()), headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except Exception as e:
        print('no previous candhis.json:', e); return {}

def main():
    os.makedirs(OUT, exist_ok=True)
    if not KEY:
        print('CANDHIS_KEY not set: Candhis skipped'); return
    now = int(time.time() * 1000); day = time.strftime('%Y-%m-%d', time.gmtime())
    prev = previous()
    st = prev.get('state') or {}
    if st.get('day') != day: st = {'day': day, 'count': 0, 'last': st.get('last', {})}
    last = {int(k): v for k, v in (st.get('last') or {}).items()}
    rows = {r['code']: r for r in prev.get('rows', [])}
    base = prev.get('base') or BASES[0]; auth = prev.get('auth') or AUTHS[0]; stop = None
    combos = [(base, auth)] + [(b, a) for b in BASES for a in AUTHS if (b, a) != (base, auth)]
    for typ in (2, 1, 0):
        if stop: break
        if now - last.get(typ, 0) < (EVERY[typ] - 3) * 60000: continue
        if st['count'] + 1 > DAILY_CAP: print('daily cap reached (%d requests)' % st['count']); break
        j = None; n401 = 0
        for b, a in (combos if not prev.get('ok') else [(base, auth)] + combos[1:]):
            if st['count'] + 1 > DAILY_CAP: break
            try:
                st['count'] += 1; j = call(b, 'getCampListeTR.php', auth=a, type=typ); base, auth = b, a; break
            except urllib.error.HTTPError as e:
                body = ''
                try: body = e.read().decode('utf-8', 'replace')[:200]
                except Exception: pass
                print('type %d on %s (%s): HTTP %d %s' % (typ, b, 'Bearer' if a.startswith('Bearer') else 'raw key', e.code, body))
                if e.code in (423, 429): stop = 'HTTP %d' % e.code; break
                if e.code == 401: n401 += 1; continue
                break
            except Exception as e:
                print('type %d on %s: %s' % (typ, b, e))
        if not j and n401 == len(combos): stop = 'HTTP 401 (key refused)'
        if not j: continue
        if str(j.get('success')).lower() != 'true': print('type %d: %s' % (typ, j.get('message'))); continue
        new = parse(j, typ); last[typ] = now
        for r in new: rows[r['code']] = r
        print('type %d: %d buoys' % (typ, len(new)))
        time.sleep(1)
    st['last'] = last
    data = {'updated': now, 'source': 'Candhis - Cerema (Licence Ouverte Etalab)', 'base': base, 'auth': auth, 'ok': bool(last), 'error': stop,
            'state': st, 'rows': sorted(rows.values(), key=lambda r: r['code'])}
    with open(os.path.join(OUT, 'candhis.json'), 'w') as f: json.dump(data, f, separators=(',', ':'))
    print('%d Candhis buoys, %d requests today' % (len(rows), st['count']))

if __name__ == '__main__':
    main()
