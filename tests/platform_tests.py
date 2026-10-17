"""Platform tests (run from /workspace/apify/deploy): python3 ../actors/google-trends-scraper/tests/platform_tests.py T1 [T2 ...]"""
import json, sys
sys.path.insert(0, '/workspace/apify/deploy')
import deploy as d
T = {
 'T1': {'searchTerms': ['air fryer'], 'geos': ['US'], 'timeRange': 'past-12-months'},
 'T2': {'comparisonGroups': ['chatgpt, gemini, claude, copilot, perplexity'], 'geos': ['', 'US', 'GB', 'DE', 'IN'], 'timeRange': 'past-90-days'},
 'T3': {'searchTerms': ['pizza', 'sushi', 'tacos', 'ramen', 'burger', 'pho', 'falafel', 'kebab', 'curry', 'dumplings'], 'geos': ['US'], 'timeRange': 'past-5-years', 'maxConcurrency': 5},
 'T4': {'trendingNowGeos': ['US', 'GB', 'IL'], 'maxTrendingPerGeo': 10},
 'T5': {'searchTerms': ['zzqxv nonexistent term 9137'], 'geos': ['US-CA'], 'timeRange': '2024-01-01 2024-06-30', 'searchProperty': 'youtube'},
 'T6': {'searchTerms': [], 'geos': ['United States']},
 'T8': {'searchTerms': ['keyword %d' % i for i in range(1)] + ['iphone', 'samsung', 'nike', 'adidas', 'netflix', 'spotify', 'tesla', 'bitcoin', 'ethereum', 'gold price', 'weather', 'football', 'taylor swift', 'mortgage rates', 'flights', 'hotels', 'yoga', 'protein powder', 'electric bike', 'solar panels'], 'geos': ['US', 'GB', 'AU'], 'timeRange': 'past-12-months', 'maxConcurrency': 6},
 'T7': {'searchTerms': ['bitcoin'], 'geos': ['US'], 'timeRange': 'past-day', 'includeRelatedTopics': False, 'regionResolution': 'DMA'},
}
for t in sys.argv[1:]:
    r = d.run('google-trends-scraper', T[t], wait=600)
    run = r['run']; items = r['items']
    kv = None
    if run['status'] == 'SUCCEEDED':
        import os, urllib.request
        kv = json.loads(urllib.request.urlopen(urllib.request.Request(f"{d.API}/key-value-stores/{run['defaultKeyValueStoreId']}/records/OUTPUT", headers={'Authorization': 'Bearer ' + os.environ['APIFY_TOKEN']}), timeout=60).read())
    reports = [i for i in items if i.get('type') == 'keywordReport']
    print(f"{t}: {run['status']} ${run.get('usageTotalUsd'):.5f} {run['stats'].get('runTimeSecs')}s | {run.get('statusMessage')}")
    for i in reports[:12]:
        print('   ', i['searchTerms'], i['geo'], 'tl', len(i.get('interestOverTime') or []), 'reg', len(i.get('interestByRegion') or []),
              'rq', {k: (len(v['top']), len(v['rising'])) for k, v in (i.get('relatedQueries') or {}).items()},
              'rt', {k: (len(v['top']), len(v['rising'])) for k, v in (i.get('relatedTopics') or {}).items()}, 'charged', i.get('charged'), i.get('error') or i.get('errors') or '')
    tr = [i for i in items if i.get('type') == 'trendingNow']
    if tr: print('    trending', len(tr), [(i['geo'], i.get('title'), i.get('approxTraffic')) for i in tr[:4]], [i.get('error') for i in tr if i.get('error')])
    print('    http', json.dumps(kv and kv.get('stats', {}).get('http')), 'proxy$', kv and kv['stats'].get('estimatedProxyCostUsd'))
