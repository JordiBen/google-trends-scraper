"""Unit tests with small synthetic responses that mirror the shapes Google Trends returns (no network)."""
import json
from urllib.parse import parse_qs, urlparse

import pytest

from src.trends import (InputError, build_groups, explore_url, normalize_geo, normalize_time, parse_geo, parse_input,
                        parse_related, parse_timeseries, parse_traffic, parse_trending_rss, select_widgets, strip_xssi,
                        trends_ui_url, widget_url)

XSSI = ")]}',\n"


def test_time_aliases_and_custom():
    assert normalize_time('past-12-months') == 'today 12-m'
    assert normalize_time('now 7-d') == 'now 7-d'
    assert normalize_time('2024-01-01 2024-12-31') == '2024-01-01 2024-12-31'
    for bad in ('yesterday', '2024-12-31 2024-01-01', '2003-01-01 2004-02-01', '2024-13-01 2024-12-01'):
        with pytest.raises(InputError):
            normalize_time(bad)


def test_geo():
    assert normalize_geo('') == '' and normalize_geo('worldwide') == ''
    assert normalize_geo('us') == 'US' and normalize_geo('uk') == 'GB'
    assert normalize_geo('US-CA') == 'US-CA' and normalize_geo('US-NY-501') == 'US-NY-501'
    with pytest.raises(InputError):
        normalize_geo('United States')


def test_groups_dedupe_and_limit():
    g = build_groups(['Coffee', 'coffee ', 'tea'], ['a, b', 'A,B', ['x', 'y', 'x']])
    assert g == [['Coffee'], ['tea'], ['a', 'b'], ['x', 'y']]
    with pytest.raises(InputError):
        build_groups([], ['1,2,3,4,5,6'])


def test_parse_input_defaults_and_errors():
    c = parse_input({'searchTerms': ['air fryer']})
    assert c['geos'] == [''] and c['time'] == 'today 12-m' and c['property'] == ''
    assert c['overTime'] and c['byRegion'] and c['queries'] and c['topics']
    assert parse_input({'searchTerms': ['x'], 'searchProperty': 'shopping'})['property'] == 'froogle'
    with pytest.raises(InputError):
        parse_input({})
    with pytest.raises(InputError):
        parse_input({'trendingNowGeos': ['']})
    assert parse_input({'trendingNowGeos': ['us', 'US']})['trendingGeos'] == ['US']


def test_explore_url_and_ui_url():
    u = explore_url(['a b', 'c'], 'US', 'today 12-m', 71, 'youtube', 'en-US')
    q = parse_qs(urlparse(u).query)
    req = json.loads(q['req'][0])
    assert req['comparisonItem'][1] == {'keyword': 'c', 'geo': 'US', 'time': 'today 12-m'}
    assert req['category'] == 71 and req['property'] == 'youtube' and q['tz'] == ['0']
    assert trends_ui_url(['a b', 'c'], 'US', 'today 12-m', 0, '') == 'https://trends.google.com/trends/explore?q=a%20b%2Cc&date=today%2012-m&geo=US'


EXPLORE_COMPARE = {'widgets': [
    {'id': 'TIMESERIES', 'token': 't1', 'request': {'time': 'x'}},
    {'id': 'GEO_MAP', 'token': 't2', 'request': {'resolution': 'REGION'}},
    {'id': 'TITLE_0'},
    {'id': 'GEO_MAP_0', 'token': 't3', 'request': {}},
    {'id': 'RELATED_QUERIES_0', 'token': 't4', 'request': {}},
    {'id': 'GEO_MAP_1', 'token': 't5', 'request': {}},
    {'id': 'RELATED_QUERIES_1', 'token': 't6', 'request': {}},
]}
EXPLORE_SINGLE = {'widgets': [
    {'id': 'TIMESERIES', 'token': 't1', 'request': {}}, {'id': 'GEO_MAP', 'token': 't2', 'request': {}},
    {'id': 'RELATED_TOPICS', 'token': 't3', 'request': {}}, {'id': 'RELATED_QUERIES', 'token': 't4', 'request': {}}]}


def test_select_widgets_compare_uses_combined_map():
    cfg = parse_input({'searchTerms': ['a']})
    ids = [w['id'] for w in select_widgets(EXPLORE_COMPARE, cfg, 2)]
    assert ids == ['TIMESERIES', 'GEO_MAP', 'RELATED_QUERIES_0', 'RELATED_QUERIES_1']
    ids = [w['id'] for w in select_widgets(EXPLORE_SINGLE, cfg, 1)]
    assert ids == ['TIMESERIES', 'GEO_MAP', 'RELATED_TOPICS', 'RELATED_QUERIES']
    cfg2 = parse_input({'searchTerms': ['a'], 'includeInterestByRegion': False, 'includeRelatedTopics': False})
    assert [w['id'] for w in select_widgets(EXPLORE_SINGLE, cfg2, 1)] == ['TIMESERIES', 'RELATED_QUERIES']


def test_widget_url_sets_resolution():
    cfg = parse_input({'searchTerms': ['a']})
    for geo, res in (('', 'COUNTRY'), ('US', 'REGION'), ('US-CA', 'CITY')):
        q = parse_qs(urlparse(widget_url(EXPLORE_SINGLE['widgets'][1], cfg, geo)).query)
        assert json.loads(q['req'][0])['resolution'] == res and q['token'] == ['t2']
    assert '/widgetdata/multiline?' in widget_url(EXPLORE_SINGLE['widgets'][0], cfg, '')
    assert '/widgetdata/relatedsearches?' in widget_url(EXPLORE_SINGLE['widgets'][2], cfg, '')


def test_strip_xssi():
    assert strip_xssi(XSSI + '{"a":1}') == {'a': 1}
    with pytest.raises(ValueError):
        strip_xssi('<html>sorry</html>')


def test_parse_timeseries():
    data = {'default': {'timelineData': [
        {'time': '1760227200', 'formattedTime': 'Oct 12\u2009\u2013\u200918, 2025', 'value': [61, 33], 'hasData': [True, True]},
        {'time': '1760832000', 'formattedTime': 'Oct 19', 'value': [63, 0], 'isPartial': True}], 'averages': [62, 17]}}
    r = parse_timeseries(data, ['coffee', 'tea'])
    assert r['timeline'][0] == {'date': '2025-10-12T00:00:00Z', 'formattedTime': 'Oct 12 \u2013 18, 2025',
                                'values': {'coffee': 61, 'tea': 33}, 'isPartial': False}
    assert r['timeline'][1]['isPartial'] is True and r['averages'] == {'coffee': 62, 'tea': 17}
    assert parse_timeseries({'default': {'timelineData': [{'time': '0', 'value': [4]}, {'time': '1', 'value': [6]}]}}, ['x'])['averages'] == {'x': 5}


def test_parse_geo_sorted():
    data = {'default': {'geoMapData': [
        {'geoCode': 'US-KS', 'geoName': 'Kansas', 'value': [40], 'hasData': [True]},
        {'geoCode': 'US-HI', 'geoName': 'Hawaii', 'value': [100], 'hasData': [True]},
        {'geoCode': 'US-XX', 'geoName': 'Nowhere', 'value': [0], 'hasData': [False]}]}}
    r = parse_geo(data, ['coffee'])
    assert [x['geoCode'] for x in r] == ['US-HI', 'US-KS']


def test_parse_related_queries_and_topics():
    q = {'default': {'rankedList': [
        {'rankedKeyword': [{'query': 'coffee near me', 'value': 100, 'formattedValue': '100', 'link': '/trends/explore?q=coffee+near+me'}]},
        {'rankedKeyword': [{'query': 'new drink', 'value': 5000, 'formattedValue': 'Breakout'},
                           {'query': 'cold brew', 'value': 250, 'formattedValue': '+250%'}]}]}}
    r = parse_related(q, 'RELATED_QUERIES')
    assert r['top'][0]['query'] == 'coffee near me' and r['top'][0]['link'].startswith('https://trends.google.com/trends/explore')
    assert r['rising'][0]['isBreakout'] and not r['rising'][1]['isBreakout']
    t = {'default': {'rankedList': [{'rankedKeyword': [{'topic': {'mid': '/m/02vqfm', 'title': 'Coffee', 'type': 'Drink'}, 'value': 100, 'formattedValue': '100'}]}, {'rankedKeyword': []}]}}
    r = parse_related(t, 'RELATED_TOPICS')
    assert r['top'][0] == {'topic': 'Coffee', 'topicType': 'Drink', 'topicId': '/m/02vqfm', 'value': 100,
                           'formattedValue': '100', 'isBreakout': False, 'link': None}
    assert parse_related({'default': {'rankedList': []}}, 'RELATED_TOPICS') == {'top': [], 'rising': []}


RSS = '''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>storm alpha</title><ht:approx_traffic>2,000+</ht:approx_traffic><pubDate>Sat, 17 Oct 2026 01:30:00 -0700</pubDate>
<ht:picture>https://example.org/p.jpg</ht:picture><ht:picture_source>Example News</ht:picture_source>
<ht:news_item><ht:news_item_title>Storm nears coast</ht:news_item_title><ht:news_item_url>https://example.org/a</ht:news_item_url><ht:news_item_source>Example</ht:news_item_source></ht:news_item></item>
<item><title>match day</title><ht:approx_traffic>100K+</ht:approx_traffic></item>
<item><title>third</title></item>
</channel></rss>'''


def test_parse_trending_rss():
    r = parse_trending_rss(RSS, 'US', 2)
    assert len(r) == 2 and r[0]['rank'] == 1 and r[0]['title'] == 'storm alpha'
    assert r[0]['approxTrafficNumber'] == 2000 and r[1]['approxTrafficNumber'] == 100_000
    assert r[0]['publishedAt'] == '2026-10-17T08:30:00Z'
    assert r[0]['news'][0] == {'title': 'Storm nears coast', 'url': 'https://example.org/a', 'source': 'Example', 'picture': None}


def test_parse_traffic():
    assert parse_traffic('1M+') == 1_000_000 and parse_traffic('500+') == 500 and parse_traffic(None) is None and parse_traffic('lots') is None
