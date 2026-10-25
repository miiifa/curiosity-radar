"""Offline v1 contract and publication failure fixtures."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect


def fixture():
    return {'mode': 'live', 'generated_at': '2020-01-01T00:00:00Z', 'errors': [],
            'items': [{'id': 'ai-test', 'category': 'ai', 'title': 'Public fixture',
                       'source': 'Fixture', 'url': 'https://example.com/article',
                       'published': None, 'score': 50}]}


class SnapshotTests(unittest.TestCase):
    def test_checked_in_snapshot(self):
        collect.validate_snapshot(json.loads(collect.OUTPUT.read_text()))

    def test_old_live_and_demo_remain_distinct(self):
        data = fixture()
        collect.validate_snapshot(data)  # Age alone must not invalidate retained data.
        self.assertFalse(collect.recent(data['generated_at']))
        data['mode'] = 'demo'
        data['items'][0]['demo'] = True
        collect.validate_snapshot(data)
        for mode, flag in [('live', True), ('demo', False)]:
            with self.subTest(mode=mode):
                data['mode'] = mode
                data['items'][0]['demo'] = flag
                with self.assertRaises(ValueError):
                    collect.validate_snapshot(data)

    def test_missing_fields_and_invalid_values(self):
        base = fixture()
        for key in ('id', 'category', 'title', 'source', 'url', 'published', 'score'):
            with self.subTest(missing=key):
                data = copy.deepcopy(base)
                del data['items'][0][key]
                with self.assertRaises(ValueError):
                    collect.validate_snapshot(data)
        for key, value in [('url', 'javascript:alert(1)'), ('url', 'https://'),
                           ('url', 'https://user:secret@example.com'),
                           ('url', 'https://example.com:bad'), ('url', 'https://example.com/\n'),
                           ('category', 'unknown'), ('score', True), ('score', -1),
                           ('score', 101), ('score', float('nan')),
                           ('published', '2026-02-30T00:00:00Z'),
                           ('published', '2026-01-01T00:00:00'), ('demo', 'false')]:
            with self.subTest(key=key, value=value):
                data = copy.deepcopy(base)
                data['items'][0][key] = value
                with self.assertRaises(ValueError):
                    collect.validate_snapshot(data)
        for key, value in [('mode', 'stale'), ('generated_at', None),
                           ('generated_at', 'invalid'), ('items', []), ('errors', 'error')]:
            with self.subTest(key=key):
                data = {**base, key: value}
                with self.assertRaises(ValueError):
                    collect.validate_snapshot(data)
        data = copy.deepcopy(base)
        data['items'] *= 2
        with self.assertRaises(ValueError):
            collect.validate_snapshot(data)

    def test_all_sources_fail_preserves_exact_bytes_and_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'news.json'
            output.write_text(json.dumps(fixture()))
            before = output.read_bytes()
            with patch.object(collect, 'OUTPUT', output), \
                 patch.object(collect, 'read_github', return_value=[]), \
                 patch.object(collect, 'read_feed_sources', return_value=[]), \
                 patch.object(collect, 'read_kev', return_value=[]), \
                 patch.object(collect, 'read_hacker_news', return_value=[]), \
                 patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(collect.main(), 1)
            self.assertEqual(output.read_bytes(), before)

    def test_invalid_candidate_and_replace_failure_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'news.json'
            output.write_text(json.dumps(fixture()))
            before = output.read_bytes()
            with patch.object(collect, 'OUTPUT', output):
                with self.assertRaises(ValueError):
                    collect.save_snapshot({**fixture(), 'mode': 'unknown'})
                with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
                    with self.assertRaises(OSError):
                        collect.save_snapshot(fixture())
                self.assertEqual(output.read_bytes(), before)
                self.assertEqual(list(Path(directory).iterdir()), [output])
                collect.save_snapshot(fixture())
                collect.validate_snapshot(json.loads(output.read_text()))

    def test_partial_success_retains_live_items_not_demo_and_receives_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'news.json'
            previous = fixture()
            previous['items'][0]['published'] = collect.NOW.isoformat()
            previous['items'].append({**previous['items'][0], 'id': 'demo', 'demo': True})
            output.write_text(json.dumps(previous))
            new = {**previous['items'][0], 'id': 'new', 'url': 'https://example.com/new'}
            with patch.object(collect, 'OUTPUT', output), \
                 patch.object(collect, 'read_github', return_value=[]) as github, \
                 patch.object(collect, 'read_feed_sources', return_value=[new]), \
                 patch.object(collect, 'read_kev', return_value=[]), \
                 patch.object(collect, 'read_hacker_news', return_value=[]), \
                 patch.object(collect, 'ERRORS', ['Fixture: TimeoutError']), \
                 patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(collect.main(), 0)
                github.assert_called_once_with(previous)
            result = json.loads(output.read_text())
            self.assertEqual({x['id'] for x in result['items']}, {'ai-test', 'new'})
            self.assertEqual(result['errors'], ['Fixture: TimeoutError'])
            self.assertEqual(result['mode'], 'live')

    def test_error_metadata_does_not_copy_exception_secrets(self):
        with patch.object(collect, 'get_bytes', side_effect=OSError('secret-token-value')), \
             patch.object(collect, 'ERRORS', []):
            self.assertEqual(collect.read_hacker_news(), [])
            self.assertEqual(collect.ERRORS, ['Hacker News: OSError'])

    def test_star_delta_uses_previous_snapshot(self):
        repo = {'full_name': 'fixture/tool', 'html_url': 'https://github.com/fixture/tool',
                'stargazers_count': 120, 'pushed_at': collect.NOW.isoformat(), 'topics': ['automation']}
        previous = {'items': [{'category': 'github', 'url': repo['html_url'], 'stars': 100}]}
        with patch.object(collect, 'get_bytes', return_value=json.dumps({'items': [repo]}).encode()), \
             patch.object(collect.time, 'sleep'), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(collect.read_github(previous)[0]['star_delta'], 20)
