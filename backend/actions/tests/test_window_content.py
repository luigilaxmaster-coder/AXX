import unittest
from backend.actions.windows_automation import summarize_window_content
from backend.actions.desktop import validate_inputs
from backend.commands import ADAPTERS


class WindowContentTests(unittest.TestCase):
    def row(self, url, y=10, **extra):
        return dict(control_id='a'*64, control_type='ControlType.Hyperlink', name='Video',
                    value=url, automation_id='video-title', bounds={'x':10, 'y':y}, **extra)

    def test_reads_observed_links_in_visual_order_without_fabricating_urls(self):
        result = summarize_window_content({'controls':[
            self.row('https://www.youtube.com/watch?v=bbbbbbbbbbb', y=20),
            self.row('https://www.youtube.com/watch?v=aaaaaaaaaaa', y=5),
            self.row('javascript:alert(1)'), self.row('https://user:secret@example.com'),
            self.row('https://example.com', offscreen=True),
            self.row('https://youtube.com.evil.example/watch?v=ccccccccccc')
        ]})
        self.assertEqual(result['links'][0]['video_id'], 'aaaaaaaaaaa')
        self.assertEqual(len(result['links']), 3)
        self.assertNotIn('video_id', next(link for link in result['links'] if 'evil.example' in link['url']))
        self.assertEqual(result['content_status'], 'observed')

    def test_empty_and_large_observations_report_limits(self):
        self.assertEqual(summarize_window_content({'controls':[]})['content_status'], 'unavailable')
        result = summarize_window_content({'controls':[{'text':'x'*25000}]})
        self.assertEqual(len(result['text']), 24000)
        self.assertTrue(result['truncated'])

    def test_read_requires_approval_and_exact_window_identity(self):
        adapter = ADAPTERS['axx.desktop.window.read']
        self.assertNotEqual(adapter['risk'], 'read')
        validate_inputs('read_window', {'window_id':'0x1234', 'pid':10, 'expected_title':'Example Domains'})
        with self.assertRaises(ValueError): validate_inputs('read_window', {'window_id':'0x1234'})
        with self.assertRaises(ValueError): validate_inputs('read_window', {'window_id':'0x1234', 'pid':0})


if __name__ == '__main__': unittest.main()
