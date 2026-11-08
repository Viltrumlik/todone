"""Haqiqiy git repo quriladi va commit sanalari orqaga suriladi,
shunda yosh hisoblash aniq tekshiriladi."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "todone.py")
DAY = 86400


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="todone-"))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test Person")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, **kw):
        env = dict(os.environ)
        env.update(kw.get("env") or {})
        return subprocess.run(["git", *args], cwd=self.tmp, check=True,
                              capture_output=True, text=True, env=env)

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def commit(self, rel, text, days_ago=0, author="Test Person"):
        self.write(rel, text)
        self.git("add", rel)
        when = time.strftime("%Y-%m-%dT%H:%M:%S",
                             time.gmtime(time.time() - days_ago * DAY))
        self.git("commit", "-q", "-m", "add " + rel,
                 env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
                      "GIT_AUTHOR_NAME": author, "GIT_COMMITTER_NAME": author,
                      "GIT_AUTHOR_EMAIL": "a@example.com",
                      "GIT_COMMITTER_EMAIL": "a@example.com"})

    def run_cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, self.tmp, *args],
                              capture_output=True, text=True)

    def markers(self, *args):
        out = self.run_cli("--json", *args)
        return json.loads(out.stdout)["markers"]


class FindingTest(Base):
    def test_every_default_tag_is_found(self):
        self.commit("a.py", "# TODO: one\n# FIXME: two\n# HACK: three\n# XXX: four\n")
        self.assertEqual(sorted(m["tag"] for m in self.markers()),
                         ["FIXME", "HACK", "TODO", "XXX"])

    def test_the_file_and_line_are_reported(self):
        self.commit("src/app.py", "x = 1\n# TODO: fix this\n")
        m = self.markers()[0]
        self.assertEqual(m["file"], "src/app.py")
        self.assertEqual(m["line"], 2)
        self.assertIn("fix this", m["text"])

    def test_comment_punctuation_is_stripped_from_the_text(self):
        self.commit("a.js", "// TODO: clean up\n")
        self.assertTrue(self.markers()[0]["text"].startswith("TODO"))

    def test_a_word_containing_a_tag_is_not_a_match(self):
        self.commit("a.py", "TODOS = 1\nmy_fixmess = 2\n")
        self.assertEqual(self.markers(), [])

    def test_only_the_asked_for_tag(self):
        self.commit("a.py", "# TODO: one\n# FIXME: two\n")
        self.assertEqual([m["tag"] for m in self.markers("--tag", "fixme")], ["FIXME"])

    def test_untracked_files_are_skipped(self):
        self.commit("a.py", "x = 1\n")
        self.write("loose.py", "# TODO: not committed\n")
        self.assertEqual(self.markers(), [])

    def test_ignored_files_are_skipped(self):
        self.write(".gitignore", "build/\n")
        self.write("build/gen.py", "# TODO: generated\n")
        self.commit("a.py", "x = 1\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        self.assertEqual(self.markers(), [])

    def test_very_long_lines_are_skipped(self):
        self.commit("bundle.js", "x;" * 900 + "// TODO: hidden\n")
        self.assertEqual(self.markers(), [])


class AgeTest(Base):
    def test_the_age_comes_from_the_line_not_the_file(self):
        self.commit("a.py", "# TODO: ancient\n", days_ago=400)
        self.assertAlmostEqual(self.markers()[0]["age_days"], 400, delta=2)

    def test_the_oldest_comes_first(self):
        self.commit("old.py", "# TODO: old\n", days_ago=300)
        self.commit("new.py", "# TODO: new\n", days_ago=5)
        self.assertEqual([m["file"] for m in self.markers()], ["old.py", "new.py"])

    def test_older_than_filters(self):
        self.commit("old.py", "# TODO: old\n", days_ago=300)
        self.commit("new.py", "# TODO: new\n", days_ago=5)
        got = self.markers("--older-than", "100")
        self.assertEqual([m["file"] for m in got], ["old.py"])

    def test_the_author_is_recorded_and_can_be_filtered(self):
        self.commit("mine.py", "# TODO: mine\n", days_ago=10, author="Alisher")
        self.commit("theirs.py", "# TODO: theirs\n", days_ago=10, author="Bobur")
        self.assertEqual([m["file"] for m in self.markers("--author", "alisher")],
                         ["mine.py"])


class CliTest(Base):
    def test_a_clean_repo_exits_zero(self):
        self.commit("a.py", "x = 1\n")
        out = self.run_cli()
        self.assertEqual(out.returncode, 0)
        self.assertIn("clean", out.stdout)

    def test_markers_exit_three_so_it_can_gate_ci(self):
        self.commit("a.py", "# TODO: something\n")
        out = self.run_cli()
        self.assertEqual(out.returncode, 3)
        self.assertIn("1 marker", out.stdout)

    def test_older_than_as_a_gate_passes_when_nothing_is_old(self):
        self.commit("a.py", "# TODO: fresh\n", days_ago=1)
        self.assertEqual(self.run_cli("--older-than", "365").returncode, 0)

    def test_the_summary_names_the_oldest(self):
        self.commit("a.py", "# TODO: ancient\n", days_ago=500)
        self.assertIn("oldest", self.run_cli().stdout)

    def test_outside_a_git_repository_it_says_so(self):
        plain = tempfile.mkdtemp(prefix="todone-plain-")
        self.addCleanup(shutil.rmtree, plain, True)
        out = subprocess.run([sys.executable, SCRIPT, plain],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("git repository", out.stderr)

    def test_a_missing_folder_is_a_usage_error(self):
        out = subprocess.run([sys.executable, SCRIPT, os.path.join(self.tmp, "nope")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)

    def test_a_negative_age_is_a_usage_error(self):
        self.assertEqual(self.run_cli("--older-than", "-5").returncode, 2)

    def test_the_author_can_be_hidden(self):
        self.commit("a.py", "# TODO: x\n", days_ago=1, author="Someone")
        self.assertNotIn("Someone", self.run_cli("--no-author").stdout)
        self.assertIn("Someone", self.run_cli().stdout)


if __name__ == "__main__":
    unittest.main()
