"""Google Trends Scraper: interest over time, interest by region, related queries & topics (up to 5 terms compared
on one scale, many countries per run) and Trending Now searches. Logged-out public, aggregated data only."""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from apify import Actor

from .client import Blocked, Fetcher
from .trends import (InputError, explore_url, parse_geo, parse_input, parse_related, parse_timeseries,
                     parse_trending_rss, select_widgets, strip_xssi, trends_ui_url, widget_index, widget_kind, widget_url)

REPORT_EVENT = 'keyword-report'
TRENDING_EVENT = 'trending-search'


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Run:
    def __init__(self, cfg: dict, fetcher: Fetcher):
        self.cfg, self.f = cfg, fetcher
        self.stop = asyncio.Event()
        self.sem = asyncio.Semaphore(cfg['concurrency'])
        self.push_lock = asyncio.Lock()
        self.stats = {'reports': 0, 'reportsFailed': 0, 'reportsPartialFree': 0, 'reportsNoDataFree': 0, 'trending': 0, 'trendingGeosFailed': 0}

    async def push(self, item: dict, event: str | None) -> bool:
        async with self.push_lock:
            if self.stop.is_set():
                return False
            res = await Actor.push_data(item, charged_event_name=event) if event else await Actor.push_data(item)
            if event and res is not None and getattr(res, 'event_charge_limit_reached', False):
                self.stop.set()
            return True

    async def report(self, terms: list[str], geo: str):
        cfg = self.cfg
        base = {'type': 'keywordReport', 'searchTerms': terms, 'isComparison': len(terms) > 1, 'geo': geo or 'WORLDWIDE',
                'timeRange': cfg['time'], 'category': cfg['category'], 'searchProperty': cfg['propertyName'],
                'trendsUrl': trends_ui_url(terms, geo, cfg['time'], cfg['category'], cfg['property'])}
        async with self.sem:
            if self.stop.is_set():
                return
            errors = []
            try:
                explore = strip_xssi(await self.f.get_text(explore_url(terms, geo, cfg['time'], cfg['category'], cfg['property'], cfg['hl'])))
            except (Blocked, ValueError) as e:
                self.stats['reportsFailed'] += 1
                await self.push({**base, 'error': f'Could not open Google Trends for this search: {e}. Not charged.', 'charged': False,
                                 'scrapedAt': now_iso()}, None)
                return
            item = {**base}
            if cfg['overTime']:
                item.update(interestOverTime=[], averages={})
            if cfg['byRegion']:
                item['interestByRegion'] = []
            if cfg['queries']:
                item['relatedQueries'] = {t: {'top': [], 'rising': []} for t in terms}
            if cfg['topics'] and len(terms) == 1:
                item['relatedTopics'] = {t: {'top': [], 'rising': []} for t in terms}
            for w in select_widgets(explore, cfg, len(terms)):
                k = widget_kind(w)
                try:
                    data = strip_xssi(await self.f.get_text(widget_url(w, cfg, geo)))
                except (Blocked, ValueError) as e:
                    errors.append(f'{k}: {e}')
                    continue
                if k == 'TIMESERIES':
                    ts = parse_timeseries(data, terms)
                    item['interestOverTime'], item['averages'] = ts['timeline'], ts['averages']
                elif k == 'GEO_MAP':
                    item['interestByRegion'] = parse_geo(data, terms)
                else:
                    idx = widget_index(w) or 0
                    term = terms[idx] if idx < len(terms) else terms[0]
                    key = 'relatedQueries' if k == 'RELATED_QUERIES' else 'relatedTopics'
                    item.setdefault(key, {})[term] = parse_related(data, k)
            item['hasData'] = bool(item.get('interestOverTime')) and any(
                any((v or 0) > 0 for v in r['values'].values()) for r in item.get('interestOverTime', []))
            if not cfg['overTime']:
                item['hasData'] = bool(item.get('interestByRegion') or any(
                    v['top'] for v in (item.get('relatedQueries') or {}).values()))
            item['scrapedAt'] = now_iso()
            if errors:
                item['errors'] = errors
                item['charged'] = False
                self.stats['reportsPartialFree'] += 1
                await self.push(item, None)
            elif not item['hasData']:
                item['charged'] = False  # Google has no data for this search: returned for transparency, not charged
                self.stats['reportsNoDataFree'] += 1
                await self.push(item, None)
            else:
                item['charged'] = True
                if await self.push(item, REPORT_EVENT):
                    self.stats['reports'] += 1
            done = self.stats['reports'] + self.stats['reportsPartialFree'] + self.stats['reportsFailed'] + self.stats['reportsNoDataFree']
            if done % 5 == 0:
                await Actor.set_status_message(f'{done} report(s) done')

    async def trending(self, geo: str):
        async with self.sem:
            if self.stop.is_set():
                return
            try:
                xml = await self.f.get_text(f'https://trends.google.com/trending/rss?geo={geo}')
                rows = parse_trending_rss(xml, geo, self.cfg['maxTrending'])
            except Exception as e:  # noqa: BLE001 - report and continue
                self.stats['trendingGeosFailed'] += 1
                await self.push({'type': 'trendingNow', 'geo': geo, 'error': f'Trending Now feed failed: {e}. Not charged.',
                                 'charged': False, 'scrapedAt': now_iso()}, None)
                return
            ts = now_iso()
            for r in rows:
                if not await self.push({**r, 'scrapedAt': ts, 'charged': True}, TRENDING_EVENT):
                    return
                self.stats['trending'] += 1


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        try:
            cfg = parse_input(inp)
        except InputError as e:
            await Actor.fail(status_message=str(e))
            return
        geos_cc = next((g[:2] for g in cfg['geos'] if g), None)
        f = Fetcher(inp.get('proxyConfiguration', {'useApifyProxy': True}), bool(inp.get('allowResidentialFallback', True)),
                    cfg['hl'], geos_cc)
        run = Run(cfg, f)
        t0 = time.time()
        n = len(cfg['groups']) * len(cfg['geos'])
        Actor.log.info(f"{len(cfg['groups'])} term group(s) x {len(cfg['geos'])} geo(s) = {n} report(s); "
                       f"Trending Now for {len(cfg['trendingGeos'])} countr(y/ies); time={cfg['time']}")
        try:
            await asyncio.gather(*(run.report(g, geo) for g in cfg['groups'] for geo in cfg['geos']),
                                 *(run.trending(geo) for geo in cfg['trendingGeos']))
        finally:
            await f.close()
        s = {**run.stats, **{'http': f.stats}, 'estimatedProxyCostUsd': f.est_cost_usd(), 'runSeconds': round(time.time() - t0, 1)}
        await Actor.set_value('OUTPUT', {'stats': s, 'input': cfg})
        Actor.log.info(f'Stats: {s}')
        if n and run.stats['reportsFailed'] == n and not run.stats['trending']:
            await Actor.fail(status_message='Google Trends rate-limited every request in this run. Nothing was charged except the run start. Please retry in a few minutes.')
            return
        msg = f"Done: {run.stats['reports']} report(s)"
        if cfg['trendingGeos']:
            msg += f", {run.stats['trending']} trending search(es)"
        free = run.stats['reportsPartialFree'] + run.stats['reportsFailed']
        if free:
            msg += f", {free} incomplete (free, see 'errors')"
        if run.stats['reportsNoDataFree']:
            msg += f", {run.stats['reportsNoDataFree']} with no Google data (free)"
        if run.stop.is_set():
            msg += ' (stopped: max charge reached)'
        await Actor.set_status_message(msg, is_terminal=True)
