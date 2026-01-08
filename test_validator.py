import unittest
from validator import validate_citations, validate_links

class TestReportUpdater(unittest.TestCase):
    def test_citation_logic(self):
        text = "This is a fact [0]. This is new [1]. \n\nSources:\n[0] Original Document\n[1] https://google.com"
        val = validate_citations(text)
        self.assertTrue(val['has_original_ref'])
        self.assertEqual(len(val['orphans_in_text']), 0)
        self.assertEqual(len(val['orphans_in_bib']), 0)

    def test_orphan_citations(self):
        text = "Fact [1]. [2] missing. \n\nSources:\n[1] Source 1"
        val = validate_citations(text)
        self.assertIn('2', val['orphans_in_text'])

    def test_links(self):
        # This might be slow or flaky based on internet, but testing dummy
        text = "Check this: https://google.com"
        count, broken = validate_links(text)
        self.assertEqual(count, 1)
        self.assertEqual(len(broken), 0)

if __name__ == '__main__':
    unittest.main()
