"""Tests for check_docs.py (TASK-001.1). Run: python3 tools/test_check_docs.py"""
import tempfile
import unittest
from pathlib import Path

import check_docs


class CheckDocsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_check(self, *args):
        return check_docs.check([str(a) for a in args])

    def test_clean_pages_pass(self):
        self.write("a.md", "# A\n\nSee [b](b.md#second-part) and [top](#a) and [site](https://example.org).\n")
        self.write("b.md", "# B\n\n## Second part\n")
        self.assertEqual(self.run_check(self.root), [])

    def test_broken_link_is_reported(self):
        self.write("a.md", "# A\n\n[gone](missing.md)\n")
        problems = self.run_check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("missing.md", problems[0])
        self.assertIn("a.md:3", problems[0])

    def test_missing_anchor_is_reported(self):
        self.write("a.md", "# A\n\n[x](b.md#nope) [y](#also-nope)\n")
        self.write("b.md", "# B\n")
        problems = self.run_check(self.root)
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("anchor" in p for p in problems))

    def test_missing_image_is_reported(self):
        self.write("a.md", "# A\n\n![a drawing](diagrams/missing.svg)\n")
        problems = self.run_check(self.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("missing.svg", problems[0])
        self.write("diagrams/missing.svg", "<svg/>")
        self.assertEqual(self.run_check(self.root), [])

    def test_links_inside_code_are_ignored(self):
        self.write("a.md", "# A\n\n```\n[x](missing.md)\n```\n\nInline `[y](gone.md)` too.\n")
        self.assertEqual(self.run_check(self.root), [])

    def test_missing_path_is_reported(self):
        problems = self.run_check(self.root / "absent.md")
        self.assertEqual(len(problems), 1)
        self.assertIn("does not exist", problems[0])

    def test_require_and_forbid(self):
        page = self.write("a.md", "# Glossary\n\nAmbassador: the owner of a boundary.\n")
        self.assertEqual(self.run_check(page, "--require", "ambassador"), [])
        self.assertIn("Embassy", self.run_check(page, "--require", "Embassy")[0])
        self.assertIn("Ambassador", self.run_check(page, "--forbid", "Ambassador")[0])
        self.assertEqual(self.run_check(page, "--forbid", "Embassy"), [])

    def test_reachable_from(self):
        self.write("index.md", "# Index\n\n[a](a.md)\n")
        self.write("a.md", "# A\n\n[b](sub/b.md)\n")
        self.write("sub/b.md", "# B\n")
        self.assertEqual(self.run_check(self.root, "--reachable-from", self.root / "index.md"), [])
        self.write("orphan.md", "# Orphan\n")
        problems = self.run_check(self.root, "--reachable-from", self.root / "index.md")
        self.assertEqual(len(problems), 1)
        self.assertIn("orphan.md", problems[0])

    def test_plans_and_hidden_directories_are_skipped_when_walking(self):
        self.write("a.md", "# A\n")
        self.write("plans/p.md", "[x](missing.md)\n")
        self.write(".venv/v.md", "[x](missing.md)\n")
        self.assertEqual(self.run_check(self.root), [])
        self.assertEqual(len(self.run_check(self.root / "plans" / "p.md")), 1)

    def test_main_exit_status(self):
        good = self.write("a.md", "# A\n")
        bad = self.write("b.md", "[x](missing.md)\n")
        self.assertEqual(check_docs.main([str(good)]), 0)
        self.assertEqual(check_docs.main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
