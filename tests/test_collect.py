import datetime as dt
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect import clean_text, deduplicate, identifier, iso_date, idea_for, parse_feed, valid_link, recent


class CollectorTests(unittest.TestCase):
    def test_rss(self):
        xml = b'<rss><channel><item><title>Headline</title><link>https://example.com/a</link><description>Short story</description><pubDate>Thu, 22 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        rows = parse_feed(xml)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['title'],'Headline')
        self.assertEqual(rows[0]['published'],'2026-10-22T12:00:00Z')

    def test_rdf_and_atom(self):
        rdf=b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><item><title>Security</title><link>https://example.com/b</link></item></rdf:RDF>'
        atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI</title><link href="https://example.com/c"/><updated>2026-10-22T09:00:00Z</updated></entry></feed>'
        self.assertEqual(parse_feed(rdf)[0]['url'],'https://example.com/b')
        self.assertEqual(parse_feed(atom)[0]['url'],'https://example.com/c')

    def test_atom_multiple_links_prefers_alternate(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Update</title><link rel="self" href="https://example.com/feed"/><link rel="alternate" href="https://example.com/article"/></entry></feed>'
        self.assertEqual(parse_feed(atom)[0]['url'],'https://example.com/article')

    def test_sanitization(self):
        self.assertEqual(clean_text('<b>Hello</b> &amp; goodbye'),'Hello & goodbye')
        self.assertFalse(valid_link('javascript:alert(1)'))

    def test_ids_and_deduplication(self):
        x={'category':'ai','url':'https://example.com','score':2}
        y={**x,'score':8}
        self.assertEqual(deduplicate([x,y]),[y])
        self.assertEqual(identifier('ai','x'),identifier('ai','x'))

    def test_dates(self):
        self.assertEqual(iso_date('2026-10-22'),'2026-10-22T00:00:00Z')
        self.assertIsNone(iso_date('invalid'))
        self.assertTrue(recent(dt.datetime.now(dt.timezone.utc).isoformat()))

    def test_idea_is_marked_unverified(self):
        repo={'url':'https://github.com/test/tool','title':'test/tool','summary':'a browser automation toolkit','tags':['automation'],'score':81,'published':None}
        result=idea_for(repo)
        self.assertEqual(result['category'],'money')
        self.assertTrue(any('未検証' in tag for tag in result['tags']))

if __name__ == '__main__':unittest.main()
