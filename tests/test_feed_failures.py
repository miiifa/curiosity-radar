"""Network failures are simulated: no external requests or snapshot writes."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect


class FeedFailureTests(unittest.TestCase):
    def test_http_200(self):
        with patch.object(collect, 'urlopen', return_value=io.BytesIO(b'fixture')):
            self.assertEqual(collect.get_bytes('https://example.com/feed'), b'fixture')

    def test_429_retries_then_succeeds(self):
        error = HTTPError('https://example.com/feed', 429, 'rate limited', {}, None)
        with patch.object(collect, 'urlopen', side_effect=[error, io.BytesIO(b'ok')]) as fetch, \
             patch.object(collect.time, 'sleep'):
            self.assertEqual(collect.get_bytes('https://example.com/feed'), b'ok')
            self.assertEqual(fetch.call_count, 2)

    def test_404_no_retry_and_429_timeout_exhaust_retries(self):
        for error, attempts in [(HTTPError('https://example.com', 404, '', {}, None), 1),
                                (HTTPError('https://example.com', 429, '', {}, None), 2),
                                (TimeoutError('private exception detail'), 2)]:
            with self.subTest(error=type(error).__name__, attempts=attempts), \
                 patch.object(collect, 'urlopen', side_effect=error) as fetch, \
                 patch.object(collect.time, 'sleep'):
                with self.assertRaises(type(error)):
                    collect.get_bytes('https://example.com/feed')
                self.assertEqual(fetch.call_count, attempts)

    def test_source_errors_and_empty_or_undated_feed(self):
        source = ('security', 'Fixture', 'https://example.com/feed', [], 30)
        undated = b'<rss><channel><item><title>Undated</title><link>https://example.com/article</link></item></channel></rss>'
        for content, reason in [(b'<broken', 'ParseError'), (b'<rss><channel/></rss>', 'EmptyFeed'),
                                (undated, 'MissingDates'), (TimeoutError('private'), 'TimeoutError'),
                                (HTTPError('https://example.com', 404, 'private', {}, None), 'HTTP404'),
                                (HTTPError('https://example.com', 429, 'private', {}, None), 'HTTP429')]:
            with self.subTest(reason=reason), patch.object(collect, 'SOURCES', [source]), \
                 patch.object(collect, 'ERRORS', []), patch('sys.stdout', new_callable=io.StringIO):
                kwargs = {'side_effect': content} if isinstance(content, Exception) else {'return_value': content}
                with patch.object(collect, 'get_bytes', **kwargs):
                    self.assertEqual(collect.read_feed_sources(), [])
                self.assertEqual(collect.ERRORS, ['RSS Fixture: ' + reason])

    def test_one_broken_source_does_not_discard_another(self):
        source = ('security', 'Broken', 'https://example.com/broken', [], 30)
        good = ('security', 'Good', 'https://example.com/good', [], 30)
        xml = f'<rss><channel><item><title>Recent</title><link>https://example.com/article</link><pubDate>{collect.NOW.isoformat()}</pubDate></item></channel></rss>'.encode()
        with patch.object(collect, 'SOURCES', [source, good]), patch.object(collect, 'ERRORS', []), \
             patch.object(collect, 'get_bytes', side_effect=[b'<broken', xml]), \
             patch('sys.stdout', new_callable=io.StringIO):
            result = collect.read_feed_sources()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['source'], 'Good')
            self.assertEqual(collect.ERRORS, ['RSS Broken: ParseError'])
