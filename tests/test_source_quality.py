"""Source health and advisory fixtures, with no network or private inventory."""
import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect


def news():
    return {'mode':'live','generated_at':collect.NOW.isoformat(),'errors':[],
            'items':[{'id':'ai-fixture','category':'ai','title':'Public fixture','source':'Fixture',
                      'url':'https://example.com/article','published':collect.NOW.isoformat(),'score':50}]}


def cve(**overrides):
    return {'cveID':'CVE-2026-12345','dateAdded':collect.NOW.date().isoformat(),
            'vendorProject':'Example vendor','product':'Example product',
            'shortDescription':'Public advisory excerpt','requiredAction':'Apply vendor updates.',**overrides}


class SourceQualityTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        self.stack.enter_context(patch.object(collect,'SOURCE_HEALTH',{}))
        self.stack.enter_context(patch.object(collect,'HEALTH_PREVIOUS',{}))
        self.stack.enter_context(patch.object(collect,'HEALTH_HISTORY_AVAILABLE',False))
        self.stack.enter_context(patch.object(collect,'ERRORS',[]))
        self.output=self.stack.enter_context(patch('sys.stdout',new_callable=io.StringIO))
        self.addCleanup(self.stack.close)

    def test_catalog_exploitation_is_not_user_impact_and_date_is_catalog_addition(self):
        with patch.object(collect,'get_bytes',return_value=json.dumps({'vulnerabilities':[cve()]}).encode()):
            rows=collect.read_kev()
        self.assertEqual(len(rows),1)
        item=rows[0]
        self.assertEqual(item['security']['exploitation_status'],'listed_in_kev')
        self.assertEqual(item['security']['user_impact'],'not_assessed')
        self.assertEqual(item['security']['kev_added_date'],cve()['dateAdded'])
        self.assertEqual(item['source_url'],collect.KEV_URL)
        self.assertEqual(item['url'],'https://nvd.nist.gov/vuln/detail/CVE-2026-12345')
        self.assertEqual(item['id'],collect.identifier('security',item['url']))
        collect.validate_snapshot({**news(),'items':rows,'source_health':list(collect.SOURCE_HEALTH.values())})

    def test_catalog_rejects_invalid_cve_dates_and_partial_rows_are_visible(self):
        bad=[cve(cveID='CVE-2026-12'),cve(cveID='javascript:alert(1)'),cve(dateAdded='2026-02-30'),cve(dateAdded='20260101')]
        with patch.object(collect,'get_bytes',return_value=json.dumps({'vulnerabilities':[cve(),*bad]}).encode()):
            rows=collect.read_kev()
        self.assertEqual(len(rows),1)
        self.assertEqual(collect.SOURCE_HEALTH['cisa-kev']['status'],'partial')
        self.assertIn('CISA KEV: InvalidCVEData',collect.ERRORS)
        with patch.object(collect,'get_bytes',return_value=json.dumps({'vulnerabilities':bad}).encode()):
            self.assertEqual(collect.read_kev(),[])
        self.assertEqual(collect.SOURCE_HEALTH['cisa-kev']['status'],'failed')

    def test_empty_or_broken_catalog_and_missing_product_do_not_invent_facts(self):
        for payload in ({'vulnerabilities':[]},{'vulnerabilities':'invalid'},[]):
            with patch.object(collect,'get_bytes',return_value=json.dumps(payload).encode()):
                self.assertEqual(collect.read_kev(),[])
            self.assertEqual(collect.SOURCE_HEALTH['cisa-kev']['status'],'failed')
        with patch.object(collect,'get_bytes',return_value=json.dumps({'vulnerabilities':[cve(vendorProject=None,product=None,requiredAction=None)]}).encode()):
            item=collect.read_kev()[0]
        self.assertIsNone(item['security']['vendor'])
        self.assertIsNone(item['security']['product'])
        self.assertIsNone(item['security']['required_action'])
        self.assertIn('製品未確認',item['title'])

    def test_rss_cve_mentions_do_not_prove_exploitation_or_user_impact(self):
        info=collect.security_metadata('Report CVE-2026-12345, cve-2026-12345, CVE-2026-12')
        self.assertEqual(info['cves'],['CVE-2026-12345'])
        self.assertEqual(info['exploitation_status'],'not_assessed')
        self.assertEqual(info['user_impact'],'not_assessed')
        self.assertEqual(collect.feed_metadata('https://jvn.jp/rss/jvn.rdf')['source_kind'],'official_feed')
        self.assertEqual(collect.feed_metadata('https://news.google.com/rss/search?q=x')['source_kind'],'search_feed')
        self.assertNotIn('source_kind',collect.feed_metadata('https://jvn.jp.example.com/feed'))

    def test_travel_query_does_not_become_verified_location_season_or_opening_hours(self):
        source=next(row for row in collect.SOURCES if row[1]=='関東発ドライブ')
        xml=f'<rss><channel><item><title>沖縄の春旅、無料イベント</title><link>https://example.com/travel</link><description>営業時間9時から17時</description><pubDate>{collect.NOW.isoformat()}</pubDate></item></channel></rss>'.encode()
        with patch.object(collect,'SOURCES',[source]),patch.object(collect,'get_bytes',return_value=xml):
            item=collect.read_feed_sources()[0]
        self.assertIn('検索条件:関東',item['tags'])
        self.assertNotIn('関東',item['tags'])
        for field in ('region','season','opening_hours','price','operating_status'):
            self.assertNotIn(field,item)
        self.assertEqual(item['source_kind'],'search_feed')

    def test_all_failure_preserves_news_but_persists_two_failures_and_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'news.json';path.write_text(json.dumps(news()))
            before=path.read_bytes()
            url='https://example.com/feed';id=collect.identifier('rss',url)
            with patch.object(collect,'OUTPUT',path):
                collect.start_health({})
                with patch.object(collect,'NOW',collect.NOW-dt.timedelta(hours=1)):
                    collect.record_health(id,'Fixture',url,1)
                success=collect.SOURCE_HEALTH[id]['last_success_at']
                collect.write_json(collect.health_path(),{'version':1,'sources':list(collect.SOURCE_HEALTH.values())})
                for attempt in (1,2):
                    with patch.object(collect,'SOURCES',[('security','Fixture',url,[],30)]), \
                         patch.object(collect,'ERRORS',[]),patch.object(collect,'get_bytes',side_effect=OSError('private-secret-do-not-log')), \
                         patch.object(collect.time,'sleep'),patch('sys.stderr',new_callable=io.StringIO):
                        self.assertEqual(collect.main(),1)
                    self.assertEqual(path.read_bytes(),before)
                    stored=json.loads(collect.health_path().read_text())
                    row=next(x for x in stored['sources'] if x['id']==id)
                    self.assertEqual(row['consecutive_failures'],attempt)
                    self.assertEqual(row['last_success_at'],success)
                    collect.validate_health(stored['sources'])
                self.assertIn('::warning::',self.output.getvalue())
                self.assertNotIn('private-secret-do-not-log',self.output.getvalue())
                self.assertNotIn('private-secret-do-not-log',collect.health_path().read_text())

    def test_corrupt_or_missing_history_does_not_invent_prior_streaks_and_success_resets(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(collect,'OUTPUT',Path(directory)/'news.json'):
            collect.health_path().write_text('{bad')
            collect.start_health({})
            collect.record_health('source','Fixture','https://example.com/feed',0,'HTTP404')
            first=collect.SOURCE_HEALTH['source']
            self.assertFalse(first['history_available'])
            self.assertEqual(first['consecutive_failures'],1)
            self.assertIsNone(first['last_success_at'])
            collect.write_json(collect.health_path(),{'version':1,'sources':[first]})
            collect.start_health({});collect.record_health('source','Fixture','https://example.com/feed',3,'IncompleteResults',partial=True)
            self.assertEqual(collect.SOURCE_HEALTH['source']['consecutive_failures'],2)
            collect.write_json(collect.health_path(),{'version':1,'sources':list(collect.SOURCE_HEALTH.values())})
            collect.start_health({});collect.record_health('source','Fixture','https://example.com/feed',3)
            self.assertEqual(collect.SOURCE_HEALTH['source']['consecutive_failures'],0)
            self.assertEqual(collect.SOURCE_HEALTH['source']['status'],'ok')
            self.assertIsNotNone(collect.SOURCE_HEALTH['source']['last_success_at'])
            demo={'mode':'demo','source_health':list(collect.SOURCE_HEALTH.values())}
            collect.health_path().unlink()
            collect.start_health(demo)
            self.assertEqual(collect.HEALTH_PREVIOUS,{})

    def test_recent_published_health_overrides_an_older_cache_after_cache_save_failure(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(collect,'OUTPUT',Path(directory)/'news.json'):
            collect.record_health('source','Fixture','https://example.com/feed',0,'HTTP404')
            old=copy.deepcopy(collect.SOURCE_HEALTH['source'])
            collect.write_json(collect.health_path(),{'version':1,'sources':[old]})
            recent={**old,'checked_at':(collect.NOW+dt.timedelta(minutes=1)).isoformat(),'last_success_at':(collect.NOW+dt.timedelta(minutes=1)).isoformat(),'status':'ok','count':1,'error':None,'consecutive_failures':0}
            collect.start_health({'source_health':[recent]})
            self.assertEqual(collect.HEALTH_PREVIOUS['source']['status'],'ok')

    def test_security_and_health_contract_rejects_unfounded_impact_and_unsafe_links(self):
        with patch.object(collect,'get_bytes',return_value=json.dumps({'vulnerabilities':[cve()]}).encode()):
            item=collect.read_kev()[0]
        for fields in ({'user_impact':'affected'},{'cves':['CVE-invalid']},{'kev_added_date':'2026-02-30'}):
            bad=copy.deepcopy(item);bad['security'].update(fields)
            with self.assertRaises(ValueError):collect.validate_snapshot({**news(),'items':[bad]})
        bad=copy.deepcopy(item);bad['source_url']='javascript:alert(1)'
        with self.assertRaises(ValueError):collect.validate_snapshot({**news(),'items':[bad]})
        row=copy.deepcopy(collect.SOURCE_HEALTH['cisa-kev']);row['count']=-1
        with self.assertRaises(ValueError):collect.validate_health([row])

    def test_invalid_hacker_news_shape_is_a_source_failure_not_an_uncaught_exception(self):
        for payload in ([],{'hits':'invalid'},{'wrong':'field'}):
            with patch.object(collect,'get_bytes',return_value=json.dumps(payload).encode()):
                self.assertEqual(collect.read_hacker_news(),[])
            self.assertEqual(collect.SOURCE_HEALTH['hacker-news']['status'],'failed')
            self.assertEqual(collect.SOURCE_HEALTH['hacker-news']['error'],'ValueError')

    def test_health_state_write_failure_is_reported_without_losing_public_news(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'news.json';output.write_text(json.dumps(news()))
            before=output.read_bytes()
            with patch.object(collect,'OUTPUT',output),patch.object(collect,'write_json',side_effect=OSError('private-path-do-not-print')), \
                 patch.object(collect,'read_github',return_value=[]),patch.object(collect,'read_feed_sources',return_value=[]), \
                 patch.object(collect,'read_kev',return_value=[]),patch.object(collect,'read_hacker_news',return_value=[]), \
                 patch('sys.stderr',new_callable=io.StringIO):
                self.assertEqual(collect.main(),1)
            self.assertEqual(output.read_bytes(),before)
            self.assertIn('history could not be saved',self.output.getvalue())
            self.assertNotIn('private-path-do-not-print',self.output.getvalue())

    def test_complete_collection_records_all_18_sources_and_writes_valid_independent_history(self):
        def fetch(url, **_kwargs):
            if url.startswith('https://api.github.com/'):
                return json.dumps({'items':[{'full_name':'fixture/tool','html_url':'https://github.com/fixture/tool',
                    'stargazers_count':120,'topics':['automation'],'pushed_at':collect.NOW.isoformat()}]}).encode()
            if url == collect.KEV_URL:
                return json.dumps({'vulnerabilities':[cve()]}).encode()
            if url.startswith('https://hn.algolia.com/'):
                return json.dumps({'hits':[]}).encode()
            link='https://example.com/'+collect.identifier('fixture',url)
            return f'<rss><channel><item><title>Public fixture</title><link>{link}</link><pubDate>{collect.NOW.isoformat()}</pubDate></item></channel></rss>'.encode()
        with tempfile.TemporaryDirectory() as directory,patch.object(collect,'OUTPUT',Path(directory)/'news.json'), \
             patch.object(collect,'get_bytes',side_effect=fetch),patch.object(collect.time,'sleep'):
            self.assertEqual(collect.main(),0)
            result=json.loads(collect.OUTPUT.read_text())
            collect.validate_snapshot(result)
            self.assertEqual(len(result['source_health']),18)
            self.assertEqual(result['sources_attempted'],18)
            self.assertTrue(all(row['status']=='ok' for row in result['source_health']))
            state=json.loads(collect.health_path().read_text())
            self.assertEqual(state['sources'],result['source_health'])
            self.assertTrue(all(row['last_success_at'] for row in state['sources']))
