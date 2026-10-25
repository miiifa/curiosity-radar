#!/usr/bin/env python3
"""Curiosity Radar public-source collector. External content is untrusted."""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import tempfile
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, unquote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'news.json'
MAX_DAYS = 40
NOW = dt.datetime.now(UTC)
ERRORS: list[str] = []
EXCLUDED_REPO_URLS: set[str] = set()
REPO_TOPICS = {'automation', 'ai-agent', 'workflow', 'mcp', 'self-hosted', 'dashboard', 'monitoring'}
USER_AGENT = 'CuriosityRadar/1.0 (personal news reader; https://github.com)'


def get_bytes(url: str, *, token: str | None = None) -> bytes:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json,application/rss+xml,application/xml,text/xml,*/*'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    request = Request(url, headers=headers)
    for attempt in range(2):
        try:
            with urlopen(request, timeout=14) as response:
                content = response.read(2_500_000)
                if len(content) >= 2_500_000:
                    raise ValueError('response exceeded size limit')
                return content
        except HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504) or attempt:
                raise
        except (URLError, TimeoutError):
            if attempt:
                raise
        time.sleep(1.2)
    raise RuntimeError('no response')


def failure_kind(exc: Exception) -> str:
    """Public diagnostic classification, never the raw response/exception text."""
    return f'HTTP{exc.code}' if isinstance(exc, HTTPError) else type(exc).__name__


def clean_text(value: str | None, limit=230) -> str:
    plain = html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))
    plain = re.sub(r'\s+', ' ', plain).strip()
    return plain[:limit - 1].rstrip() + '…' if len(plain) > limit else plain


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed:
            return parsed.astimezone(UTC).isoformat().replace('+00:00', 'Z')
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace('+00:00', 'Z')
    except ValueError:
        return None


def recent(iso: str | None, days: int = MAX_DAYS) -> bool:
    if not iso:
        return False
    try:
        posted = dt.datetime.fromisoformat(iso.replace('Z', '+00:00'))
        age = NOW - posted
        return dt.timedelta(hours=-12) <= age <= dt.timedelta(days=days)
    except (ValueError, TypeError):
        return False


def valid_link(link: str) -> bool:
    if not isinstance(link, str) or any(c.isspace() or ord(c) < 32 for c in link):
        return False
    try:
        url = urlsplit(link)
        return (url.scheme in ('http', 'https') and bool(url.hostname)
                and url.username is None and url.password is None
                and (url.port is None or 1 <= url.port <= 65535))
    except ValueError:
        return False


def identifier(kind: str, url: str) -> str:
    return kind + '-' + hashlib.sha256(url.encode()).hexdigest()[:18]


def node_text(node: ET.Element, names: list[str]) -> str:
    for name in names:
        for child in node:
            if child.tag.split('}')[-1].lower() != name.lower():
                continue
            if name == 'link' and child.get('href') and child.get('rel') not in (None, '', 'alternate'):
                continue
            if name == 'link' and child.get('href'):
                return (child.get('href') or '').strip()
            if child.text and child.text.strip():
                return child.text.strip()
    return ''


def parse_feed(blob: bytes) -> list[dict]:
    tree = ET.fromstring(blob)
    nodes = [n for n in tree.iter() if n.tag.split('}')[-1] in ('item', 'entry')]
    result = []
    for n in nodes:
        link = node_text(n, ['link'])
        title = clean_text(node_text(n, ['title']), 180)
        summary = clean_text(node_text(n, ['description', 'summary', 'encoded', 'content']), 250)
        timestamp = iso_date(node_text(n, ['pubDate', 'published', 'updated', 'date']))
        if title and valid_link(link):
            result.append({'title': title, 'summary': summary, 'url': link, 'published': timestamp})
    return result


def google_news(query: str) -> str:
    return 'https://news.google.com/rss/search?' + urlencode({'q': query, 'hl': 'ja', 'gl': 'JP', 'ceid': 'JP:ja'})


SOURCES = [
    ('ai', 'AI・テクノロジー', google_news('生成AI OR AIエージェント OR LLM when:7d'), ['AI','最新技術'], 24),
    ('ai', '海外AI開発', google_news('site:openai.com OR site:anthropic.com OR site:deepmind.google AI when:14d'), ['AI','公式動向'], 20),
    ('travel', '国内旅行のニュース', google_news('国内旅行 穴場 絶景 OR 温泉 OR 離島 when:14d'), ['国内旅行'], 26),
    ('travel', '関東発ドライブ', google_news('関東 ドライブ 日帰り 観光 OR キャンプ when:14d'), ['関東','ドライブ'], 22),
    ('social', '話題のニュース', google_news('SNS 話題 トレンド 日本 when:7d'), ['話題'], 20),
    ('hobby', 'ポケモン・ゲーム', google_news('ポケモンチャンピオンズ OR ポケモン対戦 OR ボードゲーム when:14d'), ['ゲーム','ボードゲーム'], 24),
    ('hobby', '趣味・ガジェット', google_news('ゲームマーケット OR ガジェット OR AWS 新機能 when:14d'), ['ガジェット','開発'], 17),
    ('money', '個人開発・事業化', google_news('個人開発 マイクロSaaS 収益化 OR 副業 when:14d'), ['個人開発','事業'], 18),
    ('security', 'JVN', 'https://jvn.jp/rss/jvn.rdf', ['国内','脆弱性'], 38),
    ('security', 'JPCERT/CC', 'https://www.jpcert.or.jp/rss/jpcert.rdf', ['注意喚起','国内'], 36),
    ('security', 'IPA', 'https://www.ipa.go.jp/security/alert-rss.rdf', ['重要情報','国内'], 38),
    ('security', 'Cisco Talos (脅威・脆弱性研究)', 'https://blog.talosintelligence.com/rss/', ['海外','脅威リサーチ'], 33),
]


def read_feed_sources() -> list[dict]:
    entries = []
    for category, name, url, tags, base in SOURCES:
        try:
            parsed = parse_feed(get_bytes(url))
            added = 0
            for p in parsed:
                if not recent(p['published'], 15 if category != 'security' else 30):
                    continue
                published = dt.datetime.fromisoformat(p['published'].replace('Z', '+00:00'))
                age = max(0, (NOW-published).total_seconds()/86400)
                score = round(min(96, base + max(0, 30-age*2) + (12 if category == 'security' else 0)))
                entries.append({**p, 'id': identifier(category, p['url']), 'category': category, 'source': name,
                                'tags': tags, 'reason': reason_for(category, name), 'score': score})
                added += 1
                if added >= 22:
                    break
            if not parsed:
                ERRORS.append(f'RSS {name}: EmptyFeed')
            elif all(p['published'] is None for p in parsed):
                ERRORS.append(f'RSS {name}: MissingDates')
            print(f'RSS {name}: {added} relevant of {len(parsed)} parsed')
        except (OSError, ValueError, ET.ParseError, RuntimeError) as exc:
            ERRORS.append(f'RSS {name}: {failure_kind(exc)}')
    return entries


def reason_for(category: str, source: str) -> str:
    return {
        'ai': 'AIの具体的な活用や新機能につながる可能性。一次情報で詳細を確認。',
        'travel': '週末の候補探しに。アクセス・営業日・季節条件は要確認。',
        'money': '課題と顧客がいるかを小さく検証する出発点。収益性は未検証。',
        'security': '注意喚起・修正情報を確認し、利用サービスへの影響を判断。',
        'social': 'ネット上で取り上げられた話題。Xのポストランキングではない。',
        'hobby': 'ゲームや制作の次の趣味・試作につながる情報。',
    }.get(category, f'{source}から取得')


def read_kev() -> list[dict]:
    url = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
    try:
        data = json.loads(get_bytes(url))
        items = []
        for row in data.get('vulnerabilities', []):
            iso = iso_date(row.get('dateAdded'))
            if not recent(iso, 21):
                continue
            cve = row.get('cveID','')
            if not re.fullmatch(r'CVE-\d{4}-\d{4,}',cve):
                continue
            link = f'https://nvd.nist.gov/vuln/detail/{cve}'
            items.append({'id': identifier('security', link), 'category':'security',
                'title':f"悪用確認: {row.get('vendorProject','')} {row.get('product','')} / {cve}",
                'summary': clean_text(row.get('shortDescription',''),235), 'url':link,
                'source':'CISA KEV', 'published':iso, 'tags':['KEV','悪用確認',cve],
                'reason':'CISAのKEV登録。実際に悪用が確認された脆弱性。該当製品の影響と対応を確認。', 'score':95})
        print(f'CISA KEV: {len(items)} recent CVEs')
        return items[:38]
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        ERRORS.append(f'CISA KEV: {failure_kind(exc)}')
        return []


def repo_topics(repo: dict) -> set[str]:
    values = repo.get('topics')
    return {x.lower() for x in values if isinstance(x, str)} if isinstance(values, list) else set()


def repo_license(repo: dict) -> str | None:
    info = repo.get('license')
    value = info.get('spdx_id') if isinstance(info, dict) else None
    return value if isinstance(value, str) and value and value not in ('NOASSERTION', 'OTHER') else None


def star_count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def repo_reason(repo: dict, delta: int | None) -> str:
    topics = repo_topics(repo)
    if topics & {'automation', 'ai-agent', 'workflow', 'mcp'}:
        base = '公開topicsから、自動化やAI連携への応用を検討する候補（用途は未検証）。'
    elif topics & {'self-hosted', 'dashboard', 'monitoring'}:
        base = '公開topicsから、自前運用や監視ツールへの応用を検討する候補（用途は未検証）。'
    else:
        base = '公開メタデータをもとに用途を調べる候補。'
    if not repo_license(repo):
        base += ' ライセンス未確認。利用条件の確認が必要。'
    return base


def repo_score(repo: dict, daily_delta: float | None) -> int:
    stars = star_count(repo.get('stargazers_count')) or 0
    created = iso_date(repo.get('created_at'))
    age = max(1, (NOW-dt.datetime.fromisoformat(created.replace('Z','+00:00'))).days) if created else 60
    velocity = stars / max(7,age)
    score = 34 + min(30,math.log10(stars+1)*11) + min(25,math.log10(1+velocity)*16)
    if daily_delta is not None:
        score += min(15, math.log1p(max(0,daily_delta))*4)
    return max(10,min(99,int(score)))


def star_observation(repo: dict, prior: dict | None) -> dict:
    stars = star_count(repo.get('stargazers_count'))
    old = star_count(prior.get('stars')) if prior else None
    delta = stars - old if stars is not None and old is not None else None
    since = None
    raw_time = prior.get('stars_observed_at') if prior else None
    if isinstance(raw_time, str) and 'T' in raw_time:
        try:
            parsed = dt.datetime.fromisoformat(raw_time.replace('Z','+00:00'))
            if parsed.utcoffset() is not None:
                since = iso_date(raw_time)
        except ValueError:
            pass
    elapsed = (NOW-dt.datetime.fromisoformat(since.replace('Z','+00:00'))).total_seconds() if since else 0
    if elapsed <= 0:
        since = None
    # Short intervals amplify noise. Keep the actual difference, but no rate/rising claim.
    rate = delta * 86400 / elapsed if delta is not None and elapsed >= 3600 else None
    percent = rate / max(1, old) * 100 if rate is not None else None
    return {'stars': stars, 'stars_observed_at': NOW.isoformat().replace('+00:00','Z') if stars is not None else None,
            'star_delta': delta, 'star_delta_since': since if delta is not None else None,
            'star_delta_per_day': round(rate, 6) if rate is not None else None,
            'star_growth_percent_per_day': round(percent, 6) if percent is not None else None}


def select_repos(items: list[dict]) -> list[dict]:
    """Reserve bounded, disjoint discovery pools; never fabricate a missing pool."""
    groups = {key: [] for key in ('small', 'rising', 'established', 'other')}
    for item in sorted(items, key=lambda x: (-x['score'], x['id'])):
        group = item.get('discovery_group')
        groups[group if group in groups else 'other'].append(item)
    caps = {'small': 12, 'rising': 8, 'established': 9, 'other': 29}
    groups = {key: values[:caps[key]] for key, values in groups.items()}
    result = []
    while any(groups.values()) and len(result) < 29:
        for values in groups.values():
            if values and len(result) < 29:
                result.append(values.pop(0))
    return result


def read_github(previous: dict) -> list[dict]:
    EXCLUDED_REPO_URLS.clear()
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    since = (NOW-dt.timedelta(days=80)).strftime('%Y-%m-%d')
    # Keep the four-request budget, but let the new/small query escape the star leaderboard.
    queries = [(f'created:>{since} stars:30..9999 fork:false archived:false', 'updated'),
               (f'topic:ai-agent pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=30 fork:false archived:false', 'stars'),
               (f'topic:automation pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=30 fork:false archived:false', 'stars'),
               (f'topic:self-hosted pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=30 fork:false archived:false', 'stars')]
    repo_map = {}
    for q, sort in queries:
        uri='https://api.github.com/search/repositories?'+urlencode({'q':q+' is:public','sort':sort,'order':'desc','per_page':'25'})
        try:
            payload = json.loads(get_bytes(uri,token=token))
            if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
                raise ValueError('invalid GitHub search response')
            if payload.get('incomplete_results'):
                ERRORS.append('GitHub search: IncompleteResults')
            for repo in payload['items']:
                if not isinstance(repo, dict):
                    continue
                url = repo.get('html_url')
                if not valid_link(url) or urlsplit(url).scheme != 'https' or urlsplit(url).netloc != 'github.com':
                    continue
                if not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', urlsplit(url).path) or urlsplit(url).query or urlsplit(url).fragment:
                    continue
                if repo.get('archived') or repo.get('fork') or repo.get('disabled') or repo.get('private') or repo.get('visibility') in ('private', 'internal'):
                    EXCLUDED_REPO_URLS.add(url)
                    continue
                if not repo_topics(repo) & REPO_TOPICS:
                    EXCLUDED_REPO_URLS.add(url)
                    continue
                repo_map[url] = repo
            print(f'GitHub search: {len(payload.get("items",[]))} rows')
        except (OSError, ValueError, RuntimeError) as exc:
            ERRORS.append(f'GitHub search: {failure_kind(exc)}')
        time.sleep(.3)
    previous_repos = {x.get('url'): x for x in previous.get('items', [])
                      if x.get('category') == 'github' and not x.get('demo')}
    if previous.get('mode') == 'demo':
        previous_repos = {}
    all_repos=[]
    for url, repo in repo_map.items():
        if url in EXCLUDED_REPO_URLS:
            continue
        observation = star_observation(repo, previous_repos.get(url))
        stars = observation['stars']
        rate = observation['star_delta_per_day']
        percent = observation['star_growth_percent_per_day']
        if rate is not None and rate >= 5 and percent >= 1:
            group = 'rising'
        elif stars is not None and 30 <= stars < 10000:
            group = 'small'
        elif stars is not None and stars >= 10000:
            group = 'established'
        else:
            group = None
        all_repos.append({'id': identifier('github',url), 'category':'github', 'url':url,
            'title':repo.get('full_name') or 'Unnamed GitHub project',
            'summary':clean_text(repo.get('description') or 'READMEを確認してください。'),
            'published':iso_date(repo.get('pushed_at')), 'source':'GitHub Search API',
            **observation, 'discovery_group':group,
            'language':repo.get('language'),'license':repo_license(repo),
            'tags':sorted(repo_topics(repo))[:5], 'reason':repo_reason(repo,observation['star_delta']),
            'score':repo_score(repo,rate)})
    return select_repos(all_repos)


def idea_for(repo: dict) -> dict:
    text = (' '.join([repo.get('title',''),repo.get('summary','')] + repo.get('tags',[]))).lower()
    if any(t in text for t in ['browser','automation','workflow','scrape']):
        title='中小事業者向けの作業自動化サポート'
        summary='繰り返し作業の時間を減らせるか、まず一業種・一業務で検証。外部サービスの利用規約、個人情報、保守費用を確認。'
        tag='自動化'
    elif re.search(r'(?<![a-z])(ai|agent|llm|mcp)(?![a-z])', text):
        title='業務特化のAIミニツール'
        summary='特定の業種・作業に絞った小さなAIツールの受託開発・月額提供を検証。API従量課金と誤回答への対策が必要。'
        tag='AIサービス'
    elif any(t in text for t in ['dashboard','monitor','feed','rss','news']):
        title='ニッチ情報を届ける有料ダッシュボード'
        summary='収集した情報を整理し、特定の職種に役立つレポートとして提供できるか調査。情報の再配布許諾に注意。'
        tag='情報サービス'
    elif any(t in text for t in ['game','board']):
        title='ゲームコミュニティ向けの分析ツール'
        summary='対戦データ分析や便利機能を小規模なアプリにする仮説。ゲームの利用規約と著作権を確認。'
        tag='ゲーム'
    else:
        title='OSSの導入・カスタマイズ支援'
        summary='導入の難しいOSSを特定の業種向けに整備し、初期設定や継続保守のニーズを確認。商用利用可能なライセンスか要確認。'
        tag='受託開発'
    return {'id': identifier('money',repo['url']), 'category':'money', 'url':repo['url'],
        'title':title+' — '+repo['title'].split('/')[-1], 'summary':summary,
        'published':repo.get('published'), 'source':'着想元: '+repo['title'],
        'tags':[tag,'収益性未検証','OSS活用'], 'reason':'公開OSSから生成した仮説。顧客需要・競合・ライセンス・費用は未検証。',
        'score': min(93,repo['score']-3)}


def read_hacker_news() -> list[dict]:
    try:
        uri='https://hn.algolia.com/api/v1/search?'+urlencode({'tags':'front_page','hitsPerPage':25})
        payload=json.loads(get_bytes(uri))
        out=[]
        for row in payload.get('hits',[]):
            link=row.get('url') or ('https://news.ycombinator.com/item?id='+str(row.get('objectID','')))
            title=clean_text(row.get('title') or '',160)
            posted=iso_date(row.get('created_at'))
            if not (title and valid_link(link) and recent(posted,8)):
                continue
            points=int(row.get('points') or 0)
            out.append({'id':identifier('social',link),'category':'social', 'title':title,
                'summary':f'Hacker News: {points}ポイント、{int(row.get("num_comments") or 0)}件のコメント。投稿先で内容を確認。',
                'url':link,'source':'Hacker News', 'published':posted,'tags':['海外IT','コミュニティ'],
                'reason':'技術コミュニティでの注目度を示す参考値。Xの話題とは別です。',
                'score': min(92,32 + int(math.log1p(points)*10))})
        return out
    except (OSError, ValueError, RuntimeError) as exc:
        ERRORS.append(f'Hacker News: {failure_kind(exc)}')
        return []


def canonical_url(url: str) -> str:
    """Comparison only: never replace an attributed original URL or resolve redirects."""
    if not valid_link(url):
        return url
    parts = urlsplit(url)
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if parts.port is not None and (parts.scheme, parts.port) not in (('https', 443), ('http', 80)):
        host += ':' + str(parts.port)
    # Unknown query bytes can be identifiers/signatures: do not decode/re-encode values.
    pairs = []
    for segment in parts.query.split('&') if parts.query else []:
        raw_key = segment.partition('=')[0]
        decoded_key = unquote_plus(raw_key)
        key = decoded_key.lower()
        if not key.startswith('utm_') and key not in ('fbclid', 'gclid'):
            pairs.append((decoded_key, segment))
    if len({key for key, _ in pairs}) == len(pairs):
        pairs.sort()
    fragment = parts.fragment if parts.fragment.startswith(('/', '!')) else ''
    return urlunsplit((parts.scheme, host, parts.path.rstrip('/') or '/', '&'.join(segment for _, segment in pairs), fragment))


def item_key(item: dict) -> tuple:
    kind = item.get('category') if item.get('category') in ('github', 'money') else 'news'
    return kind, canonical_url(item.get('url', ''))


def merge_duplicates(rows: list[dict]) -> dict:
    # The first row is authoritative (fresh observations must beat old high scores).
    chosen = dict(rows[0])
    aliases, categories, members = set(), set(), {}
    for row in rows:
        aliases.update(x for x in [row.get('id'), *row.get('aliases', [])] if isinstance(x, str))
        categories.update([row['category'], *row.get('categories', [])])
        records = [row, *row.get('duplicates', [])]
        for record in records:
            if all(record.get(key) for key in ('id', 'url', 'source')):
                key = (record['id'], record['url'], record['source'], record['category'])
                members.setdefault(key, {key: record.get(key) for key in ('id','url','title','source','category','published')})
    aliases.discard(chosen.get('id'))
    for key in ('aliases', 'categories', 'duplicates'):
        chosen.pop(key, None)
    if aliases:
        chosen['aliases'] = sorted(aliases)
    if len(categories) > 1:
        chosen['categories'] = sorted(categories)
    own = (chosen.get('id'), chosen.get('url'), chosen.get('source'), chosen.get('category'))
    others = [value for key, value in sorted(members.items()) if key != own]
    if others:
        chosen['duplicates'] = others
    return chosen


def deduplicate(items: list[dict]) -> list[dict]:
    groups = {}
    def order(item):
        date = iso_date(item.get('published'))
        timestamp = dt.datetime.fromisoformat(date.replace('Z','+00:00')).timestamp() if date else -math.inf
        return -item.get('score',0), -timestamp, item.get('id','')
    for item in sorted(items, key=order):
        groups.setdefault(item_key(item), []).append(item)
    return [merge_duplicates(rows) for rows in groups.values()]


def related_headlines(items: list[dict]) -> list[dict]:
    """Title similarity is a hint, never evidence for deleting another article."""
    result = [{key:value for key,value in item.items() if key != 'related'} for item in items]
    groups = {}
    for item in result:
        if item['category'] in ('github', 'money') or not item.get('published'):
            continue
        title = ' '.join(unicodedata.normalize('NFKC', item['title']).casefold().split())
        if len(title) >= 12:
            groups.setdefault(title, []).append(item)
    for rows in groups.values():
        for item in rows:
            published = dt.datetime.fromisoformat(item['published'].replace('Z','+00:00'))
            others = [other for other in rows if other['id'] != item['id']
                      and abs((published-dt.datetime.fromisoformat(other['published'].replace('Z','+00:00'))).total_seconds()) <= 48*3600]
            if others:
                item['related'] = [{key: other.get(key) for key in ('id','url','title','source','category','published')}
                                   for other in sorted(others, key=lambda x:x['id'])[:3]]
    return result


def validate_snapshot(data: dict) -> None:
    """Validate the existing v1 contract without treating old data as fresh."""
    def timestamp(value):
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError('invalid timestamp')
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('timestamp requires timezone')

    if not isinstance(data, dict) or data.get('mode') not in ('demo', 'live'):
        raise ValueError('invalid mode')
    timestamp(data.get('generated_at'))
    if not isinstance(data.get('items'), list) or not data['items']:
        raise ValueError('empty or invalid items')
    if not isinstance(data.get('errors'), list) or not all(isinstance(e, str) for e in data['errors']):
        raise ValueError('invalid errors')
    seen = set()
    for item in data['items']:
        if not isinstance(item, dict):
            raise ValueError('invalid item')
        for key in ('id', 'title', 'source'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError('missing item field: ' + key)
        if item['id'] in seen:
            raise ValueError('duplicate id')
        seen.add(item['id'])
        if item.get('category') not in ('github', 'ai', 'money', 'security', 'travel', 'social', 'hobby'):
            raise ValueError('invalid category')
        if not valid_link(item.get('url')):
            raise ValueError('invalid URL')
        score = item.get('score')
        if type(score) not in (int, float) or not 0 <= score <= 100:
            raise ValueError('invalid score')
        if 'published' not in item:
            raise ValueError('missing published')
        if item['published'] is not None:
            timestamp(item['published'])
        if 'aliases' in item and (not isinstance(item['aliases'], list) or
                not all(isinstance(value, str) and value and value != item['id'] for value in item['aliases'])):
            raise ValueError('invalid aliases')
        if 'categories' in item and (not isinstance(item['categories'], list) or item['category'] not in item['categories'] or
                not all(value in ('ai','security','travel','social','hobby') for value in item['categories'])):
            raise ValueError('invalid categories')
        for key in ('duplicates', 'related'):
            if key not in item:
                continue
            if not isinstance(item[key], list):
                raise ValueError('invalid references')
            for reference in item[key]:
                if not isinstance(reference, dict) or not all(isinstance(reference.get(field), str) and reference[field].strip()
                        for field in ('id','url','title','source','category')) or not valid_link(reference['url']):
                    raise ValueError('invalid reference')
                if reference['category'] not in ('github','ai','money','security','travel','social','hobby') or 'published' not in reference:
                    raise ValueError('invalid reference category/date')
                if reference['published'] is not None:
                    timestamp(reference['published'])
        if item['category'] == 'github':
            for key in ('stars', 'star_delta'):
                value = item.get(key)
                if value is not None and (type(value) is not int or (key == 'stars' and value < 0)):
                    raise ValueError('invalid star count')
            for key in ('stars_observed_at', 'star_delta_since'):
                if item.get(key) is not None:
                    timestamp(item[key])
            for key in ('star_delta_per_day', 'star_growth_percent_per_day'):
                value = item.get(key)
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise ValueError('invalid star rate')
            if item.get('discovery_group') not in (None, 'small', 'rising', 'established'):
                raise ValueError('invalid discovery group')
        if 'demo' in item and type(item['demo']) is not bool:
            raise ValueError('invalid demo flag')
        if (data['mode'] == 'live' and item.get('demo')) or (data['mode'] == 'demo' and not item.get('demo')):
            raise ValueError('mixed demo/live items')

    aliases = {}
    for item in data['items']:
        for alias in item.get('aliases', []):
            if alias in seen or (alias in aliases and aliases[alias] != item['id']):
                raise ValueError('conflicting alias')
            aliases[alias] = item['id']


def save_snapshot(data: dict) -> None:
    validate_snapshot(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=OUTPUT.parent,
                                         prefix='.news-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        temporary.replace(OUTPUT)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    previous={}
    try:
        if OUTPUT.exists():previous=json.loads(OUTPUT.read_text(encoding='utf-8'))
    except (ValueError,OSError):
        pass
    EXCLUDED_REPO_URLS.clear()
    repos=read_github(previous)
    items=read_feed_sources()+read_kev()+read_hacker_news()+repos
    items.extend(idea_for(r) for r in repos[:7])
    items=deduplicate(items)
    if not items:
        print('ERROR: All sources failed; preserving existing news.json instead of publishing an empty feed.',file=sys.stderr)
        return 1
    fresh_keys={item_key(x) for x in items}
    previous_by_key={}
    for item in previous.get('items', []):
        if not item.get('demo'):
            previous_by_key.setdefault(item_key(item), []).append(item)
    items=[merge_duplicates([item, *previous_by_key.get(item_key(item), [])]) for item in items]
    github_failed=any(error.startswith('GitHub search:') for error in ERRORS)
    previous_items=[x for x in previous.get('items',[]) if not x.get('demo') and recent(x.get('published'),15)
                    and (x.get('category') != 'github' or github_failed)
                    and x.get('url') not in EXCLUDED_REPO_URLS
                    and item_key(x) not in fresh_keys]
    items=deduplicate(items+previous_items)
    github_items=select_repos([x for x in items if x['category']=='github'])
    others=sorted((x for x in items if x['category']!='github'), key=lambda x:x.get('score',0),reverse=True)
    items=sorted(github_items+others[:360-len(github_items)],key=lambda x:x.get('score',0),reverse=True)
    items=related_headlines(items)
    result={'generated_at':NOW.isoformat().replace('+00:00','Z'), 'mode':'live', 'items':items,
            'errors':ERRORS,'sources_attempted':len(SOURCES)+6, 'collector_version':1}
    save_snapshot(result)
    print(f'Wrote {len(items)} items; {len(ERRORS)} sources failed.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
