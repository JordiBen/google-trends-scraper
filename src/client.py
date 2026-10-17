"""HTTP sessions for Google Trends with proxy rotation, cookie bootstrap, 429 backoff and residential fallback."""
from __future__ import annotations

import asyncio
import random
import uuid

import httpx
from apify import Actor

UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
]


class Blocked(Exception):
    pass


class Session:
    def __init__(self, proxy_url: str | None, hl: str):
        self.ua = random.choice(UAS)
        self.client = httpx.AsyncClient(proxy=proxy_url, timeout=45, follow_redirects=True, http2=False, headers={
            'User-Agent': self.ua, 'Accept-Language': f'{hl},en;q=0.8', 'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://trends.google.com/trends/explore'})
        self.ready = False
        self.uses = 0

    async def close(self):
        await self.client.aclose()


class Fetcher:
    """Shared pool. tier 0 = user proxy (default Apify datacenter), tier 1 = RESIDENTIAL fallback."""

    def __init__(self, proxy_input: dict | None, allow_residential: bool, hl: str, country_hint: str | None):
        self.proxy_input = proxy_input
        self.allow_residential = allow_residential
        self.hl = hl
        self.country_hint = country_hint
        self.tier = 0
        self.pcs: dict[int, object] = {}
        self.pool: list[Session] = []
        self.stats = {'requests': 0, 'ok': 0, 'rateLimited': 0, 'errors': 0, 'sessionsCreated': 0,
                      'bytesByTier': {'0': 0, '1': 0}, 'requestsByTier': {'0': 0, '1': 0}, 'switchedToResidential': False}
        self.consecutive_blocks = 0
        self.lock = asyncio.Lock()

    async def _proxy_config(self, tier: int):
        if tier in self.pcs:
            return self.pcs[tier]
        pc = None
        try:
            if tier == 0:
                if self.proxy_input and (self.proxy_input.get('useApifyProxy') or self.proxy_input.get('proxyUrls')):
                    pc = await Actor.create_proxy_configuration(actor_proxy_input=self.proxy_input)
            else:
                pc = await Actor.create_proxy_configuration(groups=['RESIDENTIAL'], country_code=self.country_hint or 'US')
        except Exception as e:  # local run without proxy access
            Actor.log.warning(f'Proxy tier {tier} unavailable: {e}')
        self.pcs[tier] = pc
        return pc

    async def _new_session(self) -> Session:
        pc = await self._proxy_config(self.tier)
        url = await pc.new_url(session_id=uuid.uuid4().hex[:12]) if pc else None
        s = Session(url, self.hl)
        s.tier = self.tier
        self.stats['sessionsCreated'] += 1
        return s

    async def acquire(self) -> Session:
        async with self.lock:
            while self.pool:
                s = self.pool.pop()
                if s.tier == self.tier:
                    return s
                await s.close()
        return await self._new_session()

    async def release(self, s: Session, good: bool):
        if good and s.uses < 40 and s.tier == self.tier:
            async with self.lock:
                self.pool.append(s)
        else:
            await s.close()

    async def _bootstrap(self, s: Session):
        try:
            r = await s.client.get('https://trends.google.com/trends/explore', params={'hl': self.hl})
            self._count(s, r)
        except httpx.HTTPError:
            pass
        s.ready = True

    def _count(self, s: Session, r: httpx.Response):
        k = str(s.tier)
        self.stats['requests'] += 1
        self.stats['requestsByTier'][k] += 1
        self.stats['bytesByTier'][k] += len(r.content) + 600  # + approx headers

    async def get_text(self, url: str, max_attempts: int = 8) -> str:
        last = None
        for attempt in range(max_attempts):
            s = await self.acquire()
            good = False
            try:
                if not s.ready:
                    await self._bootstrap(s)
                r = await s.client.get(url)
                s.uses += 1
                self._count(s, r)
                if r.status_code == 200 and r.text:
                    self.stats['ok'] += 1
                    self.consecutive_blocks = 0
                    good = True
                    return r.text
                if r.status_code == 429 or 'sorry/index' in str(r.url):
                    self.stats['rateLimited'] += 1
                    last = 'HTTP 429 (Google rate limit)'
                    await self._on_block()
                else:
                    self.stats['errors'] += 1
                    last = f'HTTP {r.status_code}'
                    if r.status_code in (400, 404):
                        raise ValueError(f'Google Trends rejected the request ({r.status_code}).')
            except httpx.HTTPError as e:
                self.stats['errors'] += 1
                last = f'{type(e).__name__}'
            finally:
                await self.release(s, good)
            await asyncio.sleep(min(20, (1.5 ** attempt)) + random.random())
        raise Blocked(last or 'failed')

    async def _on_block(self):
        self.consecutive_blocks += 1
        if self.tier == 0 and self.allow_residential and self.consecutive_blocks >= 4:
            if await self._proxy_config(1):
                self.tier = 1
                self.stats['switchedToResidential'] = True
                Actor.log.info('Datacenter IPs are rate-limited by Google; switching to residential proxy.')

    def est_cost_usd(self) -> float:
        b = self.stats['bytesByTier']
        return round(b['1'] / 1e9 * 8.0 + b['0'] / 1e9 * 0.0, 5)

    async def close(self):
        for s in self.pool:
            await s.close()
        self.pool.clear()
