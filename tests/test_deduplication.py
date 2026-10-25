"""Conservative identity fixtures: a title match must never delete an event."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect


def article(id='ai-original', url='https://example.com/article', category='ai', **fields):
    return {'id':id, 'url':url,'category':category,'title':'公開された新しいモデルの検証結果について',
            'source':'Fixture','published':collect.NOW.isoformat(),'score':50,'tags':[],**fields}


class DeduplicationTests(unittest.TestCase):
    def test_tracking_fragment_case_port_and_slash_variants(self):
        variants=['https://EXAMPLE.com:443/article/?utm_source=feed&gclid=x#section',
                  'https://example.com/article?fbclid=click', 'https://example.com/article']
        for url in variants:
            self.assertEqual(collect.canonical_url(url),'https://example.com/article')
            self.assertEqual(collect.canonical_url(collect.canonical_url(url)),collect.canonical_url(url))
        rows=[article(id=f'ai-{i}',url=url,source=f'Publisher {i}') for i,url in enumerate(variants)]
        result=collect.deduplicate(rows)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['url'],variants[0])
        self.assertEqual(set(result[0]['aliases']),{'ai-1','ai-2'})
        self.assertEqual({x['source'] for x in result[0]['duplicates']},{'Publisher 1','Publisher 2'})
        self.assertEqual(len(rows),3)  # Do not mutate caller data.

    def test_semantic_query_values_protocol_ports_and_spa_routes_stay_distinct(self):
        pairs=[('https://example.com/a?id=1','https://example.com/a?id=2'),
               ('https://example.com/a?page=1','https://example.com/a?page=2'),
               ('https://example.com/a?lang=ja','https://example.com/a?lang=en'),
               ('http://example.com/a','https://example.com/a'),
               ('https://example.com:8443/a','https://example.com/a'),
               ('https://example.com/#/story1','https://example.com/#/story2'),
               ('https://example.com/a?tag=one&tag=two','https://example.com/a?tag=two&tag=one'),
               ('https://example.com/a%2Fb','https://example.com/a/b'),
               ('https://example.com/a?flag','https://example.com/a?flag='),
               ('https://example.com/a?id=%2F','https://example.com/a?id=/')]
        for left,right in pairs:
            with self.subTest(left=left):
                self.assertNotEqual(collect.canonical_url(left),collect.canonical_url(right))
                self.assertEqual(len(collect.deduplicate([article(url=left),article(id='other',url=right)])),2)
        self.assertEqual(collect.canonical_url('https://example.com/a?b=2&a=1'),collect.canonical_url('https://example.com/a?a=1&b=2'))

    def test_same_url_cross_category_news_retains_categories_and_repo_ideas_stay_separate(self):
        rows=[article(),article(id='security-alias',category='security',score=80),
              article(id='github-repo',category='github'),article(id='money-idea',category='money')]
        result=collect.deduplicate(rows)
        self.assertEqual(len(result),3)
        news=next(x for x in result if x['category']=='security')
        self.assertEqual(news['categories'],['ai','security'])
        self.assertEqual(news['aliases'],['ai-original'])
        self.assertEqual(news['id'],'security-alias')

    def test_same_headline_distinct_urls_are_only_related_not_merged(self):
        rows=[article(),article(id='other',url='https://other.example/article',source='Other publisher')]
        result=collect.related_headlines(collect.deduplicate(rows))
        self.assertEqual(len(result),2)
        self.assertEqual([x['id'] for x in result[0]['related']],['other'])
        self.assertEqual(result[1]['related'][0]['id'],'ai-original')
        self.assertEqual(result[0]['url'],rows[0]['url'])

    def test_different_events_generic_titles_and_missing_dates_do_not_merge(self):
        older=(collect.NOW-dt.timedelta(days=4)).isoformat()
        for changes in ({'published':older},{'published':None},{'title':'重要なお知らせ'}):
            with self.subTest(changes=changes):
                first=article(title=changes.get('title',article()['title']))
                other=article(id='other',url='https://example.com/other',**changes)
                result=collect.related_headlines(collect.deduplicate([first,other]))
                self.assertEqual(len(result),2)
                self.assertTrue(all('related' not in x for x in result))

    def test_prior_aliases_survive_new_representative_and_current_data_wins(self):
        old=article(id='old',url='https://example.com/article?utm_source=old',score=99,aliases=['earliest'])
        fresh=article(id='fresh',score=10,source='Latest source')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'news.json'
            output.write_text(json.dumps({'mode':'live','items':[old]}))
            with patch.object(collect,'OUTPUT',output),patch.object(collect,'ERRORS',[]), \
                 patch.object(collect,'read_github',return_value=[]),patch.object(collect,'read_feed_sources',return_value=[fresh]), \
                 patch.object(collect,'read_kev',return_value=[]),patch.object(collect,'read_hacker_news',return_value=[]), \
                 patch('sys.stdout',new_callable=io.StringIO):
                self.assertEqual(collect.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual(len(result['items']),1)
            chosen=result['items'][0]
            self.assertEqual(chosen['id'],'fresh')
            self.assertEqual(chosen['score'],10)
            self.assertEqual(chosen['source'],'Latest source')
            self.assertEqual(set(chosen['aliases']),{'earliest','old'})
            collect.validate_snapshot(result)

    def test_duplicate_and_related_reference_contract_rejects_unsafe_data(self):
        base={'mode':'live','generated_at':collect.NOW.isoformat(),'errors':[],'items':[article()]}
        for key,value in [('aliases','wrong'),('categories',['all']),
                          ('related',[{**article(),'url':'javascript:alert(1)'}]),
                          ('duplicates',[{**article(),'published':'invalid'}])]:
            data=copy.deepcopy(base);data['items'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):collect.validate_snapshot(data)

    def test_ties_choose_newer_publication_and_alias_collisions_fail(self):
        older=article(id='a-old',published=(collect.NOW-dt.timedelta(days=1)).isoformat())
        newer=article(id='z-new')
        self.assertEqual(collect.deduplicate([older,newer])[0]['id'],'z-new')
        data={'mode':'live','generated_at':collect.NOW.isoformat(),'errors':[],
              'items':[article(id='one',aliases=['two']),article(id='two',url='https://example.com/two')]}
        with self.assertRaisesRegex(ValueError,'conflicting alias'):
            collect.validate_snapshot(data)

    def test_encoded_duplicate_query_names_keep_value_order_and_original_bytes(self):
        pairs=[('id=1&%69d=2','%69d=2&id=1'),
               ('a+b=1&a%20b=2','a%20b=2&a+b=1')]
        for left,right in pairs:
            left_url='https://example.com/article?'+left
            right_url='https://example.com/article?'+right
            with self.subTest(left=left):
                self.assertEqual(collect.canonical_url(left_url),left_url)
                self.assertEqual(collect.canonical_url(right_url),right_url)
                result=collect.deduplicate([article(url=left_url),article(id='other',url=right_url)])
                self.assertEqual(len(result),2)
        # Sorting unique decoded names still preserves the original encoded query segments.
        self.assertEqual(collect.canonical_url('https://example.com/a?z=%2F&%61=1'),'https://example.com/a?%61=1&z=%2F')
