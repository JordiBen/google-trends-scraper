"""Pure Google Trends logic: input validation, request building and response parsing (no network)."""
from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import quote, urlencode

BASE = 'https://trends.google.com'
PRESETS = {'now 1-H', 'now 4-H', 'now 1-d', 'now 7-d', 'today 1-m', 'today 3-m', 'today 12-m', 'today 5-y', 'all'}
ALIASES = {'past-hour': 'now 1-H', 'past-4-hours': 'now 4-H', 'past-day': 'now 1-d', 'past-7-days': 'now 7-d',
           'past-30-days': 'today 1-m', 'past-90-days': 'today 3-m', 'past-12-months': 'today 12-m',
           'past-5-years': 'today 5-y', 'since-2004': 'all'}
PROPERTIES = {'web': '', 'images': 'images', 'news': 'news', 'shopping': 'froogle', 'youtube': 'youtube'}
RESOLUTIONS = {'auto', 'COUNTRY', 'REGION', 'DMA', 'CITY'}
GEO_RE = re.compile(r'^[A-Z]{2}(-[A-Z0-9]{1,3}){0,2}$')
DATE_RANGE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})(T\d{2})? (\d{4}-\d{2}-\d{2})(T\d{2})?$')
MAX_TERMS_PER_GROUP = 5


class InputError(ValueError):
    pass


def clean_term(t) -> str:
    return ' '.join(str(t or '').split())[:100]


def normalize_time(t: str) -> str:
    t = ' '.join(str(t or 'today 12-m').split())
    t = ALIASES.get(t.lower(), t)
    if t in PRESETS:
        return t
    m = DATE_RANGE_RE.match(t)
    if m:
        a, b = m.group(1), m.group(3)
        try:
            da, db = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        except ValueError:
            raise InputError(f'Invalid date in timeRange "{t}".') from None
        if da > db:
            raise InputError(f'timeRange "{t}": start date is after end date.')
        if da < dt.date(2004, 1, 1):
            raise InputError('Google Trends data starts on 2004-01-01.')
        return t
    raise InputError(f'Unsupported timeRange "{t}". Use e.g. "today 12-m", "past-7-days" or "2024-01-01 2024-12-31".')


def normalize_geo(g) -> str:
    g = str(g or '').strip().upper()
    if g in ('', 'WORLD', 'WORLDWIDE', 'GLOBAL'):
        return ''
    if g == 'UK':
        g = 'GB'
    if not GEO_RE.match(g):
        raise InputError(f'Invalid geo "{g}". Use "" (worldwide), a country like "US" or a region like "US-CA".')
    return g


def build_groups(search_terms: list, comparison_groups: list) -> list[list[str]]:
    groups: list[list[str]] = []
    seen = set()
    for t in search_terms or []:
        t = clean_term(t)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            groups.append([t])
    for g in comparison_groups or []:
        parts = g if isinstance(g, list) else str(g or '').split(',')
        terms, s2 = [], set()
        for p in parts:
            p = clean_term(p)
            if p and p.lower() not in s2:
                s2.add(p.lower())
                terms.append(p)
        if not terms:
            continue
        if len(terms) > MAX_TERMS_PER_GROUP:
            raise InputError(f'Comparison group "{", ".join(terms)}" has {len(terms)} terms; Google Trends compares at most 5.')
        key = '|'.join(x.lower() for x in terms)
        if key not in seen:
            seen.add(key)
            groups.append(terms)
    return groups


def parse_input(inp: dict) -> dict:
    groups = build_groups(inp.get('searchTerms') or [], inp.get('comparisonGroups') or [])
    trending_geos = []
    for g in inp.get('trendingNowGeos') or []:
        g = normalize_geo(g)
        if not g:
            raise InputError('trendingNowGeos needs country codes like "US"; Trending Now has no worldwide feed.')
        if g not in trending_geos:
            trending_geos.append(g)
    if not groups and not trending_geos:
        raise InputError('Add at least one search term (e.g. "coffee"), a comparison group (e.g. "coffee, tea") or a Trending Now country.')
    geos = []
    for g in (inp.get('geos') if inp.get('geos') is not None else ['']) or ['']:
        g = normalize_geo(g)
        if g not in geos:
            geos.append(g)
    prop = str(inp.get('searchProperty') or 'web').lower()
    if prop not in PROPERTIES:
        raise InputError(f'searchProperty must be one of {", ".join(PROPERTIES)}.')
    res = str(inp.get('regionResolution') or 'auto')
    res = res.upper() if res.lower() != 'auto' else 'auto'
    if res not in RESOLUTIONS:
        raise InputError('regionResolution must be auto, COUNTRY, REGION, DMA or CITY.')
    try:
        cat = int(inp.get('category') or 0)
    except (TypeError, ValueError):
        raise InputError('category must be a Google Trends category number (0 = all categories).') from None
    hl = str(inp.get('language') or 'en-US')
    if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', hl):
        raise InputError('language must look like "en-US" or "de".')
    return {
        'groups': groups, 'geos': geos, 'time': normalize_time(inp.get('timeRange') or 'today 12-m'), 'category': cat,
        'property': PROPERTIES[prop], 'propertyName': prop, 'resolution': res, 'hl': hl,
        'overTime': bool(inp.get('includeInterestOverTime', True)),
        'byRegion': bool(inp.get('includeInterestByRegion', True)),
        'queries': bool(inp.get('includeRelatedQueries', True)),
        'topics': bool(inp.get('includeRelatedTopics', True)),
        'lowVolumeRegions': bool(inp.get('includeLowVolumeRegions', False)),
        'trendingGeos': trending_geos,
        'maxTrending': int(min(max(int(inp.get('maxTrendingPerGeo') or 50), 1), 100)),
        'concurrency': int(min(max(int(inp.get('maxConcurrency') or 3), 1), 10)),
    }


def explore_url(terms: list[str], geo: str, time: str, category: int, prop: str, hl: str) -> str:
    req = {'comparisonItem': [{'keyword': t, 'geo': geo, 'time': time} for t in terms], 'category': category, 'property': prop}
    return f'{BASE}/trends/api/explore?' + urlencode({'hl': hl, 'tz': '0', 'req': json.dumps(req, separators=(',', ':'))})


def trends_ui_url(terms: list[str], geo: str, time: str, category: int, prop: str) -> str:
    q = {'q': ','.join(terms), 'date': time}
    if geo:
        q['geo'] = geo
    if category:
        q['cat'] = str(category)
    if prop:
        q['gprop'] = prop
    return f'{BASE}/trends/explore?' + urlencode(q, quote_via=quote)


def strip_xssi(body: str):
    i = body.find('{')
    if i < 0:
        raise ValueError('no JSON object in Trends response')
    return json.loads(body[i:])


def widget_kind(w: dict) -> str | None:
    wid = w.get('id', '')
    for k in ('TIMESERIES', 'RELATED_QUERIES', 'RELATED_TOPICS', 'GEO_MAP'):
        if wid == k or wid.startswith(k + '_'):
            return k
    return None


def widget_index(w: dict) -> int | None:
    m = re.search(r'_(\d+)$', w.get('id', ''))
    return int(m.group(1)) if m else None


ENDPOINT = {'TIMESERIES': 'multiline', 'GEO_MAP': 'comparedgeo', 'RELATED_QUERIES': 'relatedsearches', 'RELATED_TOPICS': 'relatedsearches'}


def select_widgets(explore: dict, cfg: dict, n_terms: int) -> list[dict]:
    """Pick the widgets we need. For a comparison we use the combined GEO_MAP (all terms on one scale);
    for one term the per-term GEO_MAP_0 equals the combined map."""
    out = []
    for w in explore.get('widgets') or []:
        k = widget_kind(w)
        if not k or 'token' not in w:
            continue
        idx = widget_index(w)
        if k == 'TIMESERIES' and cfg['overTime']:
            out.append(w)
        elif k == 'GEO_MAP' and cfg['byRegion']:
            if (n_terms > 1 and idx is None) or (n_terms == 1 and idx in (None, 0)):
                if not any(widget_kind(x) == 'GEO_MAP' for x in out):
                    out.append(w)
        elif k == 'RELATED_QUERIES' and cfg['queries']:
            out.append(w)
        elif k == 'RELATED_TOPICS' and cfg['topics']:
            out.append(w)
    return out


def widget_url(w: dict, cfg: dict, geo: str) -> str:
    k = widget_kind(w)
    req = json.loads(json.dumps(w['request']))
    if k == 'GEO_MAP':
        res = cfg['resolution']
        if res == 'auto':
            res = 'COUNTRY' if not geo else ('REGION' if '-' not in geo else 'CITY')
        req['resolution'] = res
        req['includeLowSearchVolumeGeos'] = cfg['lowVolumeRegions']
    return f'{BASE}/trends/api/widgetdata/{ENDPOINT[k]}?' + urlencode({
        'hl': cfg['hl'], 'tz': '0', 'req': json.dumps(req, separators=(',', ':')), 'token': w['token']})


def _iso(ts: str | int | None) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None


def parse_timeseries(data: dict, terms: list[str]) -> dict:
    d = data.get('default') or {}
    rows = []
    for p in d.get('timelineData') or []:
        vals = p.get('value') or []
        rows.append({
            'date': _iso(p.get('time')),
            'formattedTime': (p.get('formattedTime') or '').replace('\u2009', ' '),
            'values': {t: (vals[i] if i < len(vals) else None) for i, t in enumerate(terms)},
            'isPartial': bool(p.get('isPartial', False)),
        })
    avgs = d.get('averages') or []
    if not avgs and rows:
        avgs = [round(sum((r['values'][t] or 0) for r in rows) / len(rows)) for t in terms]
    return {'timeline': rows, 'averages': {t: (avgs[i] if i < len(avgs) else None) for i, t in enumerate(terms)}}


def parse_geo(data: dict, terms: list[str]) -> list[dict]:
    out = []
    for g in (data.get('default') or {}).get('geoMapData') or []:
        vals = g.get('value') or []
        if not any(g.get('hasData') or [True]):
            continue
        out.append({'geoCode': g.get('geoCode') or None, 'geoName': g.get('geoName'),
                    'values': {t: (vals[i] if i < len(vals) else None) for i, t in enumerate(terms)}})
    out.sort(key=lambda r: -max([v for v in r['values'].values() if isinstance(v, (int, float))] or [0]))
    return out


def parse_related(data: dict, kind: str) -> dict:
    lists = (data.get('default') or {}).get('rankedList') or []
    res = {'top': [], 'rising': []}
    for name, lst in zip(('top', 'rising'), lists[:2]):
        for r in lst.get('rankedKeyword') or []:
            fv = r.get('formattedValue')
            item = {'value': r.get('value'), 'formattedValue': fv,
                    'isBreakout': name == 'rising' and isinstance(fv, str) and fv.lower() == 'breakout',
                    'link': BASE + r['link'] if r.get('link') else None}
            if kind == 'RELATED_TOPICS':
                t = r.get('topic') or {}
                item = {'topic': t.get('title'), 'topicType': t.get('type'), 'topicId': t.get('mid'), **item}
            else:
                item = {'query': r.get('query'), **item}
            res[name].append(item)
    return res


def parse_trending_rss(xml: str, geo: str, limit: int) -> list[dict]:
    """Parse https://trends.google.com/trending/rss?geo=XX (official public feed)."""
    import xml.etree.ElementTree as ET
    ns = {'ht': 'https://trends.google.com/trending/rss'}
    root = ET.fromstring(xml)
    out = []
    for rank, it in enumerate(root.iter('item'), 1):
        if len(out) >= limit:
            break
        def tx(tag, el=it):
            e = el.find(tag, ns)
            return e.text.strip() if e is not None and e.text else None
        news = [{'title': tx('ht:news_item_title', n), 'url': tx('ht:news_item_url', n), 'source': tx('ht:news_item_source', n),
                 'picture': tx('ht:news_item_picture', n)} for n in it.findall('ht:news_item', ns)]
        traffic = tx('ht:approx_traffic')
        out.append({'type': 'trendingNow', 'geo': geo, 'rank': rank, 'title': tx('title'), 'approxTraffic': traffic,
                    'approxTrafficNumber': parse_traffic(traffic), 'publishedAt': rss_date(tx('pubDate')),
                    'picture': tx('ht:picture'), 'pictureSource': tx('ht:picture_source'), 'news': news,
                    'exploreUrl': trends_ui_url([tx('title') or ''], geo, 'now 1-d', 0, '')})
    return out


def parse_traffic(s: str | None) -> int | None:
    if not s:
        return None
    m = re.match(r'^([\d.,]+)\s*([KMB]?)\+?$', s.strip().replace(' ', ''), re.I)
    if not m:
        return None
    n = float(m.group(1).replace(',', ''))
    return int(n * {'': 1, 'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}[m.group(2).upper()])


def rss_date(s: str | None) -> str | None:
    if not s:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(s).astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None
