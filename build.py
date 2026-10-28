"""Build fish.ics: FFXIV big-fish windows for the next 8 weeks, 20-min alerts.

Data: ff14-fish-tracker-app (Carbuncle Plushy fish tracker), converted to data.json.
Usage: python build.py data.json fish.txt fish.ics
"""
import json, re, sys, time
from datetime import datetime, timezone

DATA, LIST, OUT = sys.argv[1:4]
D = json.load(open(DATA))
FISH, ITEMS, SPOTS = D['FISH'], D['ITEMS'], D['FISHING_SPOTS']
WR, WT, ZONES = D['WEATHER_RATES'], D['WEATHER_TYPES'], D['ZONES']

DAYS = 56
ALERT_MIN = 20
RARE_DAYS = 3        # fish opening on average once every RARE_DAYS+ days get "!!!"
ETH = 175            # real seconds per Eorzean hour
PERIOD = 8 * ETH     # one weather period
TUG = {'light': '!', 'medium': '!!', 'heavy': '!!!'}

# ---------- Eorzean weather ----------
def target(t):
    bell = (t // ETH) % 24
    inc = (bell + 8 - bell % 8) % 24
    days = (t // 4200) & 0xFFFFFFFF
    base = (days * 100 + inc) & 0xFFFFFFFF
    s1 = ((base << 11) ^ base) & 0xFFFFFFFF
    s2 = ((s1 >> 8) ^ s1) & 0xFFFFFFFF
    return s2 % 100

def weather(terr, t):
    v = target(t)
    for w, lim in WR[str(terr)]['weather_rates']:
        if v < lim:
            return w

# ---------- windows ----------
def item_name(i):
    return ITEMS[str(i)]['name_en'].strip() if str(i) in ITEMS else str(i)

def hour_ranges(f):
    s, e = f['startHour'], f['endHour']
    if s is None or (s == 0 and e == 24):
        return [(0, 24)]
    return [(s, e)] if s < e else [(s, 24), (0, e)]

def merge(iv):
    res = []
    for a, b in sorted(iv):
        if res and a <= res[-1][1] + 0.5:
            res[-1] = (res[-1][0], max(res[-1][1], b))
        else:
            res.append((a, b))
    return res

def intersect(A, B):
    i = j = 0; res = []
    while i < len(A) and j < len(B):
        lo, hi = max(A[i][0], B[j][0]), min(A[i][1], B[j][1])
        if lo < hi: res.append((lo, hi))
        if A[i][1] < B[j][1]: i += 1
        else: j += 1
    return res

def own_windows(fid, t0, t1):
    f = FISH[str(fid)]
    terr = SPOTS[str(f['location'])]['territory_id']
    ws, pws = set(f['weatherSet']), set(f['previousWeatherSet'])
    hrs, out = hour_ranges(f), []
    p = (t0 // PERIOD) * PERIOD
    while p < t1:
        if (not ws or weather(terr, p) in ws) and (not pws or weather(terr, p - PERIOD) in pws):
            h0 = (p // ETH) % 24
            for a, b in hrs:
                lo, hi = max(a, h0), min(b, h0 + 8)
                if lo < hi:
                    out.append((p + (lo - h0) * ETH, p + (hi - h0) * ETH))
        p += PERIOD
    return merge(out)

def windows(fid, t0, t1, depth=0):
    w = own_windows(fid, t0, t1)
    for pid, _n in FISH[str(fid)]['predators']:
        if str(pid) in FISH and depth < 3:
            w = intersect(w, windows(pid, t0, t1, depth + 1))
    return w

# ---------- event text ----------
def zone(fid):
    sp = SPOTS[str(FISH[str(fid)]['location'])]
    return sp['name_en'], ZONES[str(WR[str(sp['territory_id'])]['zone_id'])]['name_en']

def wname(ids):
    return ' / '.join(WT[str(i)]['name_en'] for i in ids)

def et(h):
    return f"{int(h):02d}:{int(round((h % 1) * 60)):02d}"

def notes(fid):
    f = FISH[str(fid)]
    spot, zn = zone(fid)
    lines = [f"{item_name(fid)} — {spot}, {zn}"]
    if not (f['startHour'] == 0 and f['endHour'] == 24):
        lines.append(f"ET {et(f['startHour'])}–{et(f['endHour'])}")
    if f['previousWeatherSet'] or f['weatherSet']:
        prev = wname(f['previousWeatherSet']) + ' → ' if f['previousWeatherSet'] else ''
        lines.append(f"Weather: {prev}{wname(f['weatherSet']) or 'any'}")
    lines.append("Bait: " + ' → '.join(item_name(b) for b in f['bestCatchPath']))
    hk = [x for x in [f['hookset'] and f"{f['hookset']} hookset",
                      f['tug'] and f"{TUG.get(f['tug'], f['tug'])} tug"] if x]
    if hk: lines.append(', '.join(hk))
    if f['lure']: lines.append(f"Lure: {f['lure']} Lure")
    if f['predators']:
        lines.append("Intuition first: " + ', '.join(f"{item_name(p)} ×{n}" for p, n in f['predators']))
    if f['fishEyes']: lines.append("Fish Eyes")
    if f['folklore']: lines.append(f"Folklore: {D['FOLKLORE'][str(f['folklore'])]['book_en']}")
    return lines

def esc(s):
    return s.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

def ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def fold(line):
    out, b = [], line.encode()
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80: cut -= 1
        out.append(b[:cut].decode()); b = b[cut:]
    out.append(b.decode())
    return '\r\n '.join(out)

# ---------- main ----------
norm = lambda s: re.sub(r'[^a-z]', '', s.lower())
index = {norm(ITEMS[k]['name_en']): k for k in FISH if k in ITEMS}
wanted, unknown = {}, []
for line in open(LIST, encoding='utf-8'):
    name = line.split('#')[0].strip()
    if not name: continue
    k = index.get(norm(name))
    if k: wanted[item_name(k)] = k
    else: unknown.append(name)

T0 = int(time.time()); T1 = T0 + DAYS * 86400
YEAR = 365 * 86400
rare = set()
for n, k in wanted.items():
    count = len(windows(k, T0, T0 + YEAR))
    if not count or YEAR / 86400 / count >= RARE_DAYS:
        rare.add(n)
ev = {}
for n, k in wanted.items():
    for a, b in windows(k, T0 - 1200, T1):
        if b > T0:
            ev.setdefault((int(a), int(b)), []).append(n)

out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//FFXIV Big Fish//EN', 'CALSCALE:GREGORIAN',
       'METHOD:PUBLISH', 'X-WR-CALNAME:FFXIV Big Fish', 'X-PUBLISHED-TTL:PT6H',
       'REFRESH-INTERVAL;VALUE=DURATION:PT6H']
stamp = ts(T0)
for (a, b), names in sorted(ev.items()):
    locs = sorted({', '.join(zone(wanted[n])) for n in names})
    mins = (b - a) / 60
    desc = f"Window: {int(mins)}m{int(round((mins % 1) * 60)):02d}s\n\n" + \
           '\n\n'.join('\n'.join(notes(wanted[n])) for n in names)
    uid = '-'.join(str(wanted[n]) for n in names) + f"-{a}@ffxiv-bigfish"
    flag = '!!! ' if rare & set(names) else ''
    out += ['BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{stamp}', f'DTSTART:{ts(a)}', f'DTEND:{ts(b)}',
            fold('SUMMARY:' + esc(flag + '🐟 ' + ' + '.join(names))),
            fold('LOCATION:' + esc(' | '.join(locs))),
            fold('DESCRIPTION:' + esc(desc)),
            'BEGIN:VALARM', 'ACTION:DISPLAY', f'TRIGGER:-PT{ALERT_MIN}M',
            fold('DESCRIPTION:' + esc(flag + ' + '.join(names) + f' in {ALERT_MIN} min')), 'END:VALARM',
            'END:VEVENT']
out.append('END:VCALENDAR')
open(OUT, 'w', newline='', encoding='utf-8').write('\r\n'.join(out) + '\r\n')
print(f"{len(wanted)} fish, {len(ev)} events, until {datetime.fromtimestamp(T1, timezone.utc):%Y-%m-%d}")
print("Rare (!!!): " + (', '.join(sorted(rare)) or 'none'))
if unknown:
    print("::warning::Not found in tracker data: " + ', '.join(unknown))
