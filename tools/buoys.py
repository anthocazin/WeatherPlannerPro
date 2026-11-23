#!/usr/bin/env python3
"""Builds the buoy feed used by WeatherAssessment.html (Actual weather tab).

Source: NOAA National Data Buoy Center – latest observations of all stations
(US network + international partners: Met Office, Météo-France, Environment Canada,
JMA, TAO/PIRATA/RAMA, …). Public domain (US Government data).

Output (folder given as first argument):
  latest.json  – one row per station: last observation
  history.json – last 48 h of wave/wind observations per station (built by appending
                 the previous feed published on the buoy-data branch)
"""
import json, os, sys, time, urllib.request, calendar

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
REPO = os.environ.get('GITHUB_REPOSITORY', 'anthocazin/weatherplannerpro')
UA = {'User-Agent': 'WeatherAssessment buoy feed (github.com/%s)' % REPO}

def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')

def num(s):
    if s in ('MM', '', None): return None
    try: return float(s)
    except ValueError: return None

def main():
    os.makedirs(OUT, exist_ok=True)
    txt = get('https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt')
    names = {}
    try:
        for line in get('https://www.ndbc.noaa.gov/data/stations/station_table.txt').splitlines():
            if line.startswith('#'): continue
            p = line.split('|')
            if len(p) > 4: names[p[0].strip().upper()] = (p[4].strip() or p[3].strip())[:60]
    except Exception as e:
        print('station names unavailable:', e)
    cols = ['WDIR','WSPD','GST','WVHT','DPD','APD','MWD','PRES','PTDY','ATMP','WTMP','DEWP','VIS','TIDE']
    rows = []
    for line in txt.splitlines():
        if not line.strip() or line.startswith('#'): continue
        p = line.split()
        if len(p) < 8 + len(cols): continue
        try:
            t = calendar.timegm((int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7]), 0)) * 1000
            lat, lon = float(p[1]), float(p[2])
        except ValueError:
            continue
        v = dict(zip(cols, [num(x) for x in p[8:8+len(cols)]]))
        sid = p[0].upper()
        rows.append([sid, names.get(sid, ''), lat, lon, t, v['WVHT'], v['DPD'], v['APD'], v['MWD'],
                     v['WSPD'], v['WDIR'], v['GST'], v['WTMP'], v['ATMP'], v['PRES'], v['VIS']])
    now = int(time.time() * 1000)
    latest = {'updated': now, 'source': 'NOAA NDBC latest observations (public domain)',
              'cols': ['id','name','lat','lon','t','hs','dpd','apd','mwd','wspd','wdir','gst','wtmp','atmp','pres','vis'],
              'stations': rows}
    # rolling 48 h history
    hist = {}
    try:
        hist = json.loads(get('https://raw.githubusercontent.com/%s/buoy-data/history.json' % REPO, 30)).get('h', {})
    except Exception as e:
        print('no previous history:', e)
    cut = now - 48 * 3600 * 1000
    for r in rows:
        sid, t = r[0], r[4]
        obs = [t, r[5], r[6], r[8], r[9], r[11], r[10]]  # t, hs, dpd, mwd, wspd, gst, wdir
        if all(x is None for x in obs[1:]): continue
        h = [o for o in hist.get(sid, []) if o[0] >= cut and o[0] != t]
        h.append(obs); h.sort(key=lambda o: o[0]); hist[sid] = h
    hist = {k: v for k, v in hist.items() if v and v[-1][0] >= cut}
    with open(os.path.join(OUT, 'latest.json'), 'w') as f: json.dump(latest, f, separators=(',', ':'))
    with open(os.path.join(OUT, 'history.json'), 'w') as f:
        json.dump({'updated': now, 'cols': ['t','hs','dpd','mwd','wspd','gst','wdir'], 'h': hist}, f, separators=(',', ':'))
    print(len(rows), 'stations,', len(hist), 'with history')

if __name__ == '__main__':
    main()
