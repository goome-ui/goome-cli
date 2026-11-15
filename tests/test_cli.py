import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import goome


def add(tar, name, data=b"", mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def fake_template(path):
    with tarfile.open(path, "w:gz") as tar:
        add(tar, "tpl-main/main.c", b'#define APP_NAME "My Goome App"\n')
        add(tar, "tpl-main/run.sh", b"./my-goome-app\n", 0o755)
        add(tar, "tpl-main/src/mygoomeapp/Main.java", b"package mygoomeapp;\nclass MyGoomeApp {}\n")
        add(tar, "tpl-main/variants/hud/main.c", b"hud for my_goome_app\n")
        add(tar, "tpl-main/CONTRIBUTING.md", b"x")
        add(tar, "tpl-main/tests/check.gd", b"x")
        add(tar, "tpl-main/.github/workflows/pr-rules.yml", b"x")
        add(tar, "tpl-main/.github/workflows/ci.yml", b"run: ./my-goome-app")
        add(tar, "tpl-main/../../escape.txt", b"nope")
        add(tar, "/abs.txt", b"nope")
        link = tarfile.TarInfo("tpl-main/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.tar = os.path.join(self.dir, "tpl.tar.gz")
        fake_template(self.tar)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def new(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = goome.main(["new"] + list(args) + ["--from", self.tar])
        return rc, out.getvalue()

    def read(self, *p):
        with open(os.path.join(self.dir, *p)) as f:
            return f.read()

    def test_names(self):
        n = goome.names("cool hud-2")
        self.assertEqual(n["My Goome App"], "Cool Hud 2")
        self.assertEqual(n["my-goome-app"], "cool-hud-2")
        self.assertEqual(n["my_goome_app"], "cool_hud_2")
        self.assertEqual(n["MyGoomeApp"], "CoolHud2")
        self.assertEqual(n["mygoomeapp"], "coolhud2")
        self.assertEqual(goome.names("3d")["mygoomeapp"], "app3d")
        with self.assertRaises(SystemExit):
            goome.names("--")

    def test_app(self):
        dest = os.path.join(self.dir, "cool-hud")
        rc, out = self.new("cool-hud", "--lang", "c", "--dir", dest)
        self.assertEqual(rc, 0)
        self.assertIn("next:", out)
        self.assertEqual(self.read("cool-hud", "main.c"), '#define APP_NAME "Cool Hud"\n')
        self.assertIn("class CoolHud", self.read("cool-hud", "src", "coolhud", "Main.java"))
        self.assertIn("./cool-hud", self.read("cool-hud", ".github", "workflows", "ci.yml"))
        self.assertIn("# Cool Hud", self.read("cool-hud", "README.md"))
        for gone in ("variants", "tests", "CONTRIBUTING.md", ".github/workflows/pr-rules.yml", "link", "abs.txt"):
            self.assertFalse(os.path.exists(os.path.join(dest, gone)), gone)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "escape.txt")))
        if os.name != "nt":
            self.assertTrue(os.access(os.path.join(dest, "run.sh"), os.X_OK))
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".goome-new-")], [])

    def test_variant(self):
        dest = os.path.join(self.dir, "x")
        self.new("x", "--lang", "c", "--template", "hud", "--dir", dest)
        self.assertEqual(self.read("x", "main.c"), "hud for x\n")

    def test_missing_variant(self):
        dest = os.path.join(self.dir, "y")
        with self.assertRaises(SystemExit):
            self.new("y", "--lang", "c", "--template", "overlay", "--dir", dest)
        self.assertFalse(os.path.exists(dest))
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".goome-new-")], [])

    def test_not_empty(self):
        dest = os.path.join(self.dir, "z")
        os.makedirs(dest)
        open(os.path.join(dest, "keep"), "w").close()
        with self.assertRaises(SystemExit):
            self.new("z", "--lang", "c", "--dir", dest)
        self.assertTrue(os.path.exists(os.path.join(dest, "keep")))

    def test_list(self):
        out = io.StringIO()
        with redirect_stdout(out):
            goome.main(["list"])
        for w in ("c", "csharp", "python", "java", "godot", "app", "overlay", "mod-menu", "hud"):
            self.assertIn(w, out.getvalue())


if __name__ == "__main__":
    unittest.main()
