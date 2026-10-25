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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'news.json'
MAX_DAYS = 40
NOW = dt.datetime.now(UTC)
ERRORS: list[str] = []
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


def repo_reason(repo: dict, delta: int | None) -> str:
    topics = ' '.join(repo.get('topics',[])).lower()
    base = '改造・検証・自分のサービスへの転用を検討できるOSS。'
    if any(x in topics for x in ['automation','ai-agent','workflow','mcp']):
        base = '定型作業の自動化やAIエージェントとの連携に応用可能。'
    elif any(x in topics for x in ['self-hosted','dashboard','monitoring']):
        base = '自分で運用できるツールや監視ダッシュボード作りに応用可能。'
    if delta is not None and delta > 0:
        base += f' 前回収集からスター数が{delta}増加。'
    if not repo.get('license'):
        base += ' ライセンスが不明なので利用条件の確認が必要。'
    return base


def repo_score(repo: dict, delta: int | None) -> int:
    stars = repo.get('stargazers_count', 0)
    created = iso_date(repo.get('created_at'))
    age = max(1, (NOW-dt.datetime.fromisoformat(created.replace('Z','+00:00'))).days) if created else 60
    velocity = stars / max(7,age)
    score = 34 + min(30,math.log10(stars+1)*11) + min(25,math.log10(1+velocity)*16)
    if delta is not None:
        score += min(15, math.log1p(max(0,delta))*4)
    if repo.get('archived') or repo.get('disabled'):
        score -= 45
    return max(10,min(99,int(score)))


def read_github(previous: dict) -> list[dict]:
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    since = (NOW-dt.timedelta(days=80)).strftime('%Y-%m-%d')
    queries = [f'created:>{since} stars:>=30 fork:false archived:false',
               f'topic:ai-agent pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=80 archived:false',
               f'topic:automation pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=60 archived:false',
               f'topic:self-hosted pushed:>{(NOW-dt.timedelta(days=25)).strftime("%Y-%m-%d")} stars:>=80 archived:false']
    repo_map = {}
    for q in queries:
        uri='https://api.github.com/search/repositories?'+urlencode({'q':q,'sort':'stars','order':'desc','per_page':'25'})
        try:
            payload = json.loads(get_bytes(uri,token=token))
            for repo in payload.get('items',[]):
                if not repo.get('html_url','').startswith('https://github.com/'):
                    continue
                if repo.get('archived') or repo.get('fork'):
                    continue
                repo_map[repo['full_name']] = repo
            print(f'GitHub search: {len(payload.get("items",[]))} rows')
        except (OSError, ValueError, RuntimeError) as exc:
            ERRORS.append(f'GitHub search: {failure_kind(exc)}')
        time.sleep(.3)
    all_repos=[]
    previous_stars={x.get('url'):x.get('stars') for x in previous.get('items',[]) if x.get('category')=='github' and not x.get('demo')}
    for repo in repo_map.values():
        url = repo['html_url']
        stars=int(repo.get('stargazers_count') or 0)
        prior=previous_stars.get(url)
        delta=max(0,stars-int(prior)) if isinstance(prior,int) else None
        license_info=repo.get('license') or {}
        license_name=license_info.get('spdx_id') if isinstance(license_info,dict) else ''
        if license_name in ('NOASSERTION','OTHER'):
            license_name=''
        all_repos.append({'id': identifier('github',url), 'category':'github', 'url':url,
            'title':repo.get('full_name') or 'Unnamed GitHub project',
            'summary':clean_text(repo.get('description') or 'READMEを確認してください。'),
            'published':iso_date(repo.get('pushed_at')),
            'source':'GitHub Search API', 'stars':stars,'star_delta':delta,
            'language':repo.get('language'),'license':license_name or None,
            'tags':(repo.get('topics') or [])[:5], 'reason':repo_reason(repo,delta),
            'score':repo_score(repo,delta)})
    all_repos.sort(key=lambda x:x['score'],reverse=True)
    new_repos=[x for x in all_repos if x['stars']<10000][:12]
    established=[x for x in all_repos if x not in new_repos][:17]
    return (new_repos+established)[:29]


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


def deduplicate(items: list[dict]) -> list[dict]:
    used=set();out=[]
    for item in sorted(items,key=lambda x:(x.get('score',0),x.get('published') or ''),reverse=True):
        key=(item.get('category'),item.get('url','').split('#')[0])
        if key in used:continue
        used.add(key);out.append(item)
    return out


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
        if 'demo' in item and type(item['demo']) is not bool:
            raise ValueError('invalid demo flag')
        if (data['mode'] == 'live' and item.get('demo')) or (data['mode'] == 'demo' and not item.get('demo')):
            raise ValueError('mixed demo/live items')


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
    repos=read_github(previous)
    items=read_feed_sources()+read_kev()+read_hacker_news()+repos
    items.extend(idea_for(r) for r in repos[:7])
    items=deduplicate(items)
    if not items:
        print('ERROR: All sources failed; preserving existing news.json instead of publishing an empty feed.',file=sys.stderr)
        return 1
    previous_items=[x for x in previous.get('items',[]) if not x.get('demo') and recent(x.get('published'),15)]
    items=deduplicate(items+previous_items)
    items=sorted(items,key=lambda x:x.get('score',0),reverse=True)[:360]
    result={'generated_at':NOW.isoformat().replace('+00:00','Z'), 'mode':'live', 'items':items,
            'errors':ERRORS,'sources_attempted':len(SOURCES)+6, 'collector_version':1}
    save_snapshot(result)
    print(f'Wrote {len(items)} items; {len(ERRORS)} sources failed.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
