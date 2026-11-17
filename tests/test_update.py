import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import goome


def newer_source(version):
    return ('#!/usr/bin/env python3\n__version__ = "%s"\n' % version).encode()


class Versions(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(goome.parse_version("0.5.3"), (0, 5, 3))
        self.assertEqual(goome.parse_version("v1.10.0"), (1, 10, 0))
        self.assertEqual(goome.parse_version("0.6.0rc1"), (0, 6, 0))
        self.assertEqual(goome.parse_version("junk"), ())

    def test_newer(self):
        self.assertTrue(goome.is_newer("0.5.10", "0.5.9"))
        self.assertTrue(goome.is_newer("1.0.0", "0.9.9"))
        self.assertFalse(goome.is_newer("0.5.3", "0.5.3"))
        self.assertFalse(goome.is_newer("0.5.2", "0.5.3"))
        self.assertFalse(goome.is_newer("", "0.5.3"))


class Latest(unittest.TestCase):
    def pages(self, pypi=None, github=None):
        def fake(url, timeout=60):
            page = pypi if url == goome.PYPI_URL else github
            if page is None:
                raise OSError("no network")
            return json.dumps(page).encode()
        return fake

    def test_pip_asks_pypi_first(self):
        with mock.patch.object(goome, "installed_with_pip", return_value=True), \
                mock.patch.object(goome, "fetch", self.pages({"info": {"version": "0.9.0"}}, {"tag_name": "v0.8.0"})):
            self.assertEqual(goome.latest_version(), "0.9.0")

    def test_loose_asks_github_first(self):
        with mock.patch.object(goome, "installed_with_pip", return_value=False), \
                mock.patch.object(goome, "fetch", self.pages({"info": {"version": "0.9.0"}}, {"tag_name": "v0.8.0"})):
            self.assertEqual(goome.latest_version(), "0.8.0")

    def test_falls_back(self):
        with mock.patch.object(goome, "installed_with_pip", return_value=True), \
                mock.patch.object(goome, "fetch", self.pages(None, {"tag_name": "v0.8.0"})):
            self.assertEqual(goome.latest_version(), "0.8.0")

    def test_nothing_reachable(self):
        with mock.patch.object(goome, "fetch", self.pages(None, None)):
            self.assertIsNone(goome.latest_version())

    def test_garbage(self):
        with mock.patch.object(goome, "fetch", lambda url, timeout=60: b"<html>"):
            self.assertIsNone(goome.latest_version())


class Update(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.script = os.path.join(self.dir, "goome.py")
        with open(self.script, "wb") as f:
            f.write(newer_source("0.5.3"))
        os.chmod(self.script, 0o755)

    def tearDown(self):
        os.chmod(self.dir, 0o755)
        shutil.rmtree(self.dir)

    def run_update(self, *args, latest="0.6.0", data=None, pip=False):
        out, err = io.StringIO(), io.StringIO()
        data = newer_source(latest) if data is None else data
        with mock.patch.object(goome, "latest_version", return_value=latest), \
                mock.patch.object(goome, "installed_with_pip", return_value=pip), \
                mock.patch.object(goome, "fetch", lambda url, timeout=60: data), \
                mock.patch.object(goome, "__file__", self.script), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                rc = goome.main(["update"] + list(args))
            except SystemExit as e:
                rc = str(e)
        return rc, out.getvalue(), err.getvalue()

    def test_check(self):
        rc, out, _ = self.run_update("--check")
        self.assertEqual((rc, out.strip()), (0, "0.6.0"))

    def test_already_newest(self):
        rc, out, _ = self.run_update(latest="0.5.3")
        self.assertEqual(rc, 0)
        self.assertIn("newest", out)

    def test_no_network(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(goome, "latest_version", return_value=None), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(goome.main(["update"]), 1)
        self.assertIn("couldnt reach", err.getvalue())

    def test_replaces_and_keeps_bak(self):
        rc, out, _ = self.run_update()
        self.assertEqual(rc, 0)
        with open(self.script, "rb") as f:
            self.assertEqual(f.read(), newer_source("0.6.0"))
        with open(self.script + ".bak", "rb") as f:
            self.assertEqual(f.read(), newer_source("0.5.3"))
        self.assertEqual(sorted(os.listdir(self.dir)), ["goome.py", "goome.py.bak"])
        if os.name == "posix":
            self.assertTrue(os.stat(self.script).st_mode & stat.S_IXUSR)

    def test_wrong_version_download_is_refused(self):
        rc, _, err = self.run_update(data=newer_source("0.4.0"))
        self.assertEqual(rc, 1)
        with open(self.script, "rb") as f:
            self.assertEqual(f.read(), newer_source("0.5.3"))
        self.assertFalse(os.path.exists(self.script + ".bak"))

    def test_broken_download_is_refused(self):
        rc, _, err = self.run_update(data=b'__version__ = "0.6.0"\ndef (:\n')
        self.assertEqual(rc, 1)
        self.assertIn("broken", err)

    @unittest.skipUnless(os.name == "posix" and os.geteuid() != 0, "needs permissions that apply")
    def test_read_only_folder_is_explained(self):
        os.chmod(self.dir, 0o555)
        rc, _, _ = self.run_update()
        self.assertIn("cant write", rc)
        with open(self.script, "rb") as f:
            self.assertEqual(f.read(), newer_source("0.5.3"))

    def test_pip_install_runs_pip(self):
        calls = []
        with mock.patch.object(goome.subprocess, "call", lambda cmd: calls.append(cmd) or 0):
            rc, _, _ = self.run_update(pip=True)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [[sys.executable, "-m", "pip", "install", "-U", "goome-cli"]])

    def test_pipx_install_runs_pipx(self):
        calls = []
        prefix = os.path.join(self.dir, "pipx", "venvs", "goome-cli")
        with mock.patch.object(goome.subprocess, "call", lambda cmd: calls.append(cmd) or 0), \
                mock.patch.object(goome.sys, "prefix", prefix), \
                mock.patch.object(goome.shutil, "which", lambda n: "/usr/bin/pipx"):
            self.run_update(pip=True)
        self.assertEqual(calls, [["pipx", "upgrade", "goome-cli"]])


class Note(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.dir})
        self.env.start()
        os.environ.pop("GOOME_NO_UPDATE_CHECK", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir)

    def note(self, latest="0.9.0", tty=True):
        err = io.StringIO()
        out = mock.Mock()
        out.isatty.return_value = tty
        with mock.patch.object(goome, "latest_version", return_value=latest) as lv, \
                mock.patch.object(goome.sys, "stdout", out), redirect_stderr(err):
            goome.update_note()
        return err.getvalue(), lv

    def test_prints_once_a_day(self):
        text, _ = self.note()
        self.assertIn("0.9.0 is out", text)
        self.assertIn("goome update", text)
        text, lv = self.note()
        self.assertEqual(text, "")
        lv.assert_not_called()

    def test_checks_again_after_a_day(self):
        self.note()
        stamp = os.path.join(self.dir, "goome", "update-check")
        with open(stamp, "w") as f:
            f.write(str(time.time() - 90000))
        text, _ = self.note()
        self.assertIn("is out", text)

    def test_quiet_when_up_to_date(self):
        text, _ = self.note(latest=goome.__version__)
        self.assertEqual(text, "")

    def test_off_with_env(self):
        with mock.patch.dict(os.environ, {"GOOME_NO_UPDATE_CHECK": "1"}):
            text, lv = self.note()
        self.assertEqual(text, "")
        lv.assert_not_called()

    def test_off_without_tty(self):
        text, lv = self.note(tty=False)
        self.assertEqual(text, "")
        lv.assert_not_called()

    def test_never_fails_a_command(self):
        out = mock.Mock()
        out.isatty.return_value = True
        with mock.patch.object(goome, "latest_version", side_effect=RuntimeError("boom")), \
                mock.patch.object(goome.sys, "stdout", out):
            goome.update_note()

    def test_unwritable_cache_is_fine(self):
        with mock.patch.object(goome.os, "makedirs", side_effect=PermissionError("no")):
            text, _ = self.note()
        self.assertEqual(text, "")

    def test_list_stays_quiet_in_tests(self):
        with mock.patch.object(goome, "update_note") as n, redirect_stdout(io.StringIO()):
            goome.main(["list"])
        n.assert_called_once()


if __name__ == "__main__":
    unittest.main()
