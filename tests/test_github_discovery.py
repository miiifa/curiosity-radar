"""Public synthetic repositories; never fetch or execute third-party code."""
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect


def repo(name='small', stars=120, **extra):
    return {'full_name': 'fixture/'+name, 'html_url': 'https://github.com/fixture/'+name,
            'stargazers_count': stars, 'topics': ['automation'], 'license': {'spdx_id': 'MIT'},
            'created_at': (collect.NOW-dt.timedelta(days=30)).isoformat(),
            'pushed_at': collect.NOW.isoformat(), **extra}


def prior(value, stars=100, hours=24):
    return {'url':value['html_url'], 'category':'github', 'stars':stars,
            'stars_observed_at': (collect.NOW-dt.timedelta(hours=hours)).isoformat()}


class GithubDiscoveryTests(unittest.TestCase):
    def setUp(self):
        collect.EXCLUDED_REPO_URLS.clear()

    def tearDown(self):
        collect.EXCLUDED_REPO_URLS.clear()

    def collect(self, rows, previous=None):
        with patch.object(collect, 'get_bytes', return_value=json.dumps({'items':rows}).encode()) as fetch, \
             patch.object(collect.time,'sleep'), patch('sys.stdout',new_callable=io.StringIO):
            result=collect.read_github(previous or {})
            self.assertEqual(fetch.call_count,4)
            queries=[parse_qs(urlsplit(call.args[0]).query) for call in fetch.call_args_list]
            self.assertEqual(queries[0]['sort'],['updated'])
            self.assertIn('stars:30..9999',queries[0]['q'][0])
            self.assertTrue(all('is:public' in x['q'][0] for x in queries))
            return result

    def test_bounded_pools_include_small_rising_established_not_unrelated_giants(self):
        small=repo('small',120)
        rising=repo('rising',140)
        established=repo('established',20000)
        giants=[repo('unrelated'+str(i),1000000,topics=['unrelated']) for i in range(30)]
        rows=self.collect(giants+[small,rising,established],{'mode':'live','items':[prior(rising)]})
        self.assertEqual([x['discovery_group'] for x in rows],['small','rising','established'])
        self.assertEqual(rows[1]['star_delta'],40)
        self.assertEqual(rows[1]['star_delta_per_day'],40)
        self.assertIn('未検証',rows[0]['reason'])
        self.assertLessEqual(len(rows),29)

    def test_observation_period_is_per_repo_not_snapshot_timestamp(self):
        value=repo(stars=140)
        old=prior(value,hours=48)
        rows=self.collect([value],{'generated_at':collect.NOW.isoformat(),'items':[old]})
        self.assertEqual(rows[0]['star_delta_per_day'],20)
        self.assertEqual(rows[0]['star_growth_percent_per_day'],20)
        self.assertEqual(rows[0]['star_delta_since'],collect.iso_date(old['stars_observed_at']))
        self.assertEqual(rows[0]['stars_observed_at'],collect.NOW.isoformat().replace('+00:00','Z'))

    def test_same_growth_per_day_has_same_score_across_unequal_intervals(self):
        value=repo(stars=200)
        day=collect.star_observation(value,prior(value,stars=180,hours=24))
        half_day=collect.star_observation(value,prior(value,stars=190,hours=12))
        self.assertEqual(day['star_delta_per_day'],half_day['star_delta_per_day'])
        self.assertEqual(collect.repo_score(value,day['star_delta_per_day']),collect.repo_score(value,half_day['star_delta_per_day']))

    def test_unknown_short_future_and_demo_observations_do_not_claim_growth(self):
        value=repo(stars=120)
        for old in [None,{'stars':100}, {**prior(value),'stars_observed_at':'invalid'},
                    {**prior(value),'stars_observed_at':'2026-10-24T00:00:00'},
                    prior(value,hours=0),prior(value,hours=-1),prior(value,hours=.1),
                    prior(value,stars=True),prior(value,stars=None)]:
            with self.subTest(old=old):
                observed=collect.star_observation(value,old)
                self.assertIsNone(observed['star_delta_per_day'])
        rows=self.collect([value],{'mode':'demo','items':[prior(value)]})
        self.assertIsNone(rows[0]['star_delta'])
        self.assertEqual(rows[0]['discovery_group'],'small')

    def test_zero_negative_and_missing_stars(self):
        value=repo(stars=80)
        observed=collect.star_observation(value,prior(value))
        self.assertEqual(observed['star_delta'],-20)
        self.assertEqual(observed['star_delta_per_day'],-20)
        self.assertEqual(collect.star_observation(repo(stars=100),prior(value))['star_delta'],0)
        for stars in (None,True,-1,'120'):
            with self.subTest(stars=stars):
                observed=collect.star_observation(repo(stars=stars),prior(value))
                self.assertIsNone(observed['stars'])
                self.assertIsNone(observed['star_delta'])
                self.assertIsNone(observed['stars_observed_at'])
                self.assertTrue(10<=collect.repo_score(repo(stars=stars),None)<=99)

    def test_unsafe_archived_fork_disabled_and_unknown_license(self):
        rows=[repo('archive',archived=True),repo('fork',fork=True),repo('disabled',disabled=True),
              repo('private',private=True),repo('internal',visibility='internal'),
              repo('unsafe',html_url='https://github.com.evil.test/fixture/tool'),
              repo('credentials',html_url='https://secret@github.com/fixture/tool'),
              repo('badpath',html_url='https://github.com/fixture/tool/extra'),
              repo('unknown',license={'spdx_id':'NOASSERTION'})]
        result=self.collect(rows)
        self.assertEqual([x['title'] for x in result],['fixture/unknown'])
        self.assertIsNone(result[0]['license'])
        self.assertIn('ライセンス未確認',result[0]['reason'])
        self.assertIn(rows[0]['html_url'],collect.EXCLUDED_REPO_URLS)

    def test_current_lower_score_observation_wins_and_all_pools_survive_360_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'news.json'
            values=self.collect([repo('small'),repo('established',20000)])
            old={**values[0],'score':99,'stars':999,'stars_observed_at':(collect.NOW-dt.timedelta(days=2)).isoformat()}
            removed={**old,'id':'github-removed','url':'https://github.com/fixture/removed'}
            output.write_text(json.dumps({'mode':'live','items':[old,removed]}))
            news=[{'id':f'ai-{i}','category':'ai','title':'Fixture','url':f'https://example.com/{i}',
                   'published':collect.NOW.isoformat(),'score':100,'source':'Fixture'} for i in range(360)]
            def github(_):
                collect.EXCLUDED_REPO_URLS.add(removed['url'])
                return values
            with patch.object(collect,'OUTPUT',output), patch.object(collect,'read_github',side_effect=github), \
                 patch.object(collect,'read_feed_sources',return_value=news), patch.object(collect,'read_kev',return_value=[]), \
                 patch.object(collect,'read_hacker_news',return_value=[]), patch.object(collect,'ERRORS',[]), \
                 patch('sys.stdout',new_callable=io.StringIO):
                self.assertEqual(collect.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual(len(result['items']),360)
            github=[x for x in result['items'] if x['category']=='github']
            self.assertEqual({x['discovery_group'] for x in github},{'small','established'})
            self.assertEqual(next(x for x in github if x['id']==old['id'])['stars'],120)
            self.assertNotIn(removed['url'],[x['url'] for x in result['items']])
            collect.validate_snapshot(result)

    def test_old_repo_is_retained_only_when_github_search_is_incomplete(self):
        old=self.collect([repo()])[0]
        old['stars_observed_at']=(collect.NOW-dt.timedelta(days=2)).isoformat()
        news={'id':'ai-test','category':'ai','title':'Fixture','source':'Fixture',
              'url':'https://example.com/article','score':50,'published':collect.NOW.isoformat()}
        for errors in ([],['GitHub search: HTTP429'],['GitHub search: IncompleteResults']):
            with self.subTest(errors=errors), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'news.json'
                output.write_text(json.dumps({'mode':'live','items':[old]}))
                with patch.object(collect,'OUTPUT',output), patch.object(collect,'ERRORS',errors), \
                     patch.object(collect,'read_github',return_value=[]), \
                     patch.object(collect,'read_feed_sources',return_value=[news]), \
                     patch.object(collect,'read_kev',return_value=[]), patch.object(collect,'read_hacker_news',return_value=[]), \
                     patch('sys.stdout',new_callable=io.StringIO):
                    self.assertEqual(collect.main(),0)
                result=json.loads(output.read_text())
                retained=[x for x in result['items'] if x['category']=='github']
                self.assertEqual(bool(retained),bool(errors))
                if retained:
                    self.assertEqual(retained[0]['stars_observed_at'],old['stars_observed_at'])

    def test_incomplete_and_malformed_search_responses_keep_other_results(self):
        payloads=[json.dumps({'items':[repo()], 'incomplete_results':True}).encode(),
                  b'[]', OSError('private response detail'), json.dumps({'items':[]}).encode()]
        with patch.object(collect,'get_bytes',side_effect=payloads), patch.object(collect,'ERRORS',[]), \
             patch.object(collect.time,'sleep'), patch('sys.stdout',new_callable=io.StringIO):
            rows=collect.read_github({})
            self.assertEqual(len(rows),1)
            self.assertEqual(collect.ERRORS,['GitHub search: IncompleteResults','GitHub search: ValueError','GitHub search: OSError'])

    def test_pool_caps_and_unique_membership(self):
        items=[]
        for group in ('small','rising','established'):
            for i in range(40):
                items.append({'id':f'{group}-{i}','discovery_group':group,'score':i})
        chosen=collect.select_repos(items)
        self.assertEqual(len(chosen),29)
        self.assertEqual(len({x['id'] for x in chosen}),29)
        self.assertEqual([x['discovery_group'] for x in chosen[:3]],['small','rising','established'])
        self.assertEqual({g:sum(x['discovery_group']==g for x in chosen) for g in ('small','rising','established')},
                         {'small':12,'rising':8,'established':9})
