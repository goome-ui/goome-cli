import io
import os
import shutil
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from unittest import mock

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
        add(tar, "tpl-main/.github/update-goome.sh", b"x", 0o755)
        add(tar, "tpl-main/.github/workflows/update-goome.yml", b"x")
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
        for gone in ("variants", "tests", "CONTRIBUTING.md", ".github/workflows/pr-rules.yml", ".github/update-goome.sh", ".github/workflows/update-goome.yml", "link", "abs.txt"):
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
        for w in ("c", "csharp", "python", "java", "godot", "rust", "node", "go", "zig", "lua", "app", "overlay", "mod-menu", "hud"):
            self.assertIn(w, out.getvalue())

    def test_version(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            goome.main(["--version"])
        self.assertEqual(out.getvalue().strip(), "goome " + goome.__version__)
        self.assertRegex(goome.__version__, r"^\d+\.\d+\.\d+$")

    def lang(self, lang, step):
        dest = os.path.join(self.dir, "p-" + lang)
        rc, out = self.new("cool hud", "--lang", lang, "--dir", dest)
        self.assertEqual(rc, 0)
        self.assertIn("(%s, app template" % lang, out)
        self.assertIn("  " + step + "\n", out)
        self.assertIn(step, self.read("p-" + lang, "README.md"))

    def test_rust(self):
        self.lang("rust", "cargo run")

    def test_node(self):
        self.lang("node", "node main.js")

    def test_go(self):
        self.lang("go", "go run .")

    def test_zig(self):
        self.lang("zig", "zig build run")

    def test_lua(self):
        self.lang("lua", "lua main.lua")

    def lua_template(self, with_rockspec):
        path = os.path.join(self.dir, "lua.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            add(tar, "tpl-main/main.lua", b"print('hi')\n")
            if with_rockspec:
                add(tar, "tpl-main/goome-0.5.3-1.rockspec", b"package = 'goome'\n")
        return path

    def lua_out(self, tar, name):
        out = io.StringIO()
        with redirect_stdout(out):
            goome.main(["new", name, "--lang", "lua", "--dir", os.path.join(self.dir, name), "--from", tar])
        return out.getvalue(), self.read(name, "README.md")

    def test_lua_rockspec_named(self):
        out, readme = self.lua_out(self.lua_template(True), "withspec")
        self.assertIn("  luarocks install --local goome-0.5.3-1.rockspec\n", out)
        self.assertIn("luarocks install --local goome-0.5.3-1.rockspec", readme)
        self.assertNotIn("0.5.0", out)

    def test_lua_no_rockspec(self):
        out, readme = self.lua_out(self.lua_template(False), "nospec")
        self.assertIn("  luarocks make --local\n", out)
        self.assertNotIn(".rockspec", out)
        self.assertNotIn(".rockspec", readme)


STUB = """#!/usr/bin/env bash
case "$1" in
  *refuse*) echo "web-build: $1 isnt a goome app. overlays cant" >&2; exit 1;;
esac
mkdir -p "$2"
echo "<title>stub</title>" > "$2/index.html"
echo "$CLANG $WASM_LD $*" > "$2/args.txt"
cp "$1" "$2/goome.wasm"
echo "built $2/index.html"
"""


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, 0o755)


@unittest.skipUnless(shutil.which("bash") and os.name != "nt", "needs bash")
class Web(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.getcwd()
        self.tree = os.path.join(self.dir, "c-goome")
        os.makedirs(os.path.join(self.tree, "wasm"))
        os.makedirs(os.path.join(self.tree, "src"))
        open(os.path.join(self.tree, "src", "goome.c"), "w").close()
        with open(os.path.join(self.tree, "wasm", "web-build.sh"), "w") as f:
            f.write(STUB)
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        script(os.path.join(self.bin, "clang"), 'echo "wasm32 - WebAssembly 32-bit"\n')
        script(os.path.join(self.bin, "wasm-ld"), "exit 0\n")
        self.proj = os.path.join(self.dir, "proj")
        os.makedirs(self.proj)
        with open(os.path.join(self.proj, "main.c"), "w") as f:
            f.write("int main(void){return 0;}\n")
        os.chdir(self.proj)
        self.env = mock.patch.dict(os.environ, {"CLANG": os.path.join(self.bin, "clang"), "WASM_LD": os.path.join(self.bin, "wasm-ld"), "XDG_CACHE_HOME": os.path.join(self.dir, "cache")})
        self.env.start()
        os.environ.pop("GOOME_SRC", None)

    def tearDown(self):
        self.env.stop()
        os.chdir(self.old)
        shutil.rmtree(self.dir)

    def build(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = goome.main(["build", "--web"] + list(args))
        return rc, out.getvalue()

    def test_builds_main_c(self):
        rc, out = self.build("--goome", self.tree)
        self.assertEqual(rc, 0)
        for f in ("index.html", "goome.wasm"):
            self.assertTrue(os.path.isfile(os.path.join(self.proj, "web", f)), f)
        self.assertIn("goome serve web", out)
        with open(os.path.join(self.proj, "web", "args.txt")) as f:
            args = f.read().split()
        self.assertEqual(args[0], os.path.join(self.bin, "clang"))
        self.assertEqual(args[1], os.path.join(self.bin, "wasm-ld"))
        self.assertTrue(args[-2].endswith("main.c"))

    def test_out_and_file(self):
        with open(os.path.join(self.proj, "other.c"), "w") as f:
            f.write("x")
        self.build("other.c", "--out", "dist/site", "--goome", self.tree)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "dist", "site", "index.html")))

    def test_finds_checkout_next_to_the_app(self):
        os.chdir(self.dir)
        shutil.move(self.proj, os.path.join(self.tree, "myapp"))
        os.chdir(os.path.join(self.tree, "myapp"))
        rc, _ = self.build()
        self.assertEqual(rc, 0)

    def test_which_file(self):
        os.remove(os.path.join(self.proj, "main.c"))
        with self.assertRaises(SystemExit) as e:
            self.build("--goome", self.tree)
        self.assertIn("which file", str(e.exception))

    def test_missing_file(self):
        with self.assertRaises(SystemExit) as e:
            self.build("nope.c", "--goome", self.tree)
        self.assertIn("no such file", str(e.exception))

    def test_other_languages_by_file(self):
        for name, lang in (("Program.cs", "C#"), ("app.py", "Python"), ("App.java", "Java"), ("App.kt", "Kotlin"), ("main.rs", "Rust"), ("main.go", "Go"), ("main.zig", "Zig"), ("main.lua", "Lua"), ("app.js", "JavaScript"), ("app.ts", "TypeScript"), ("main.gd", "GDScript")):
            with open(os.path.join(self.proj, name), "w") as f:
                f.write("x")
            with self.assertRaises(SystemExit) as e:
                self.build(name, "--goome", self.tree)
            self.assertIn("only works for C apps", str(e.exception))
            self.assertIn(lang, str(e.exception))
            self.assertIn("goome.wtf/builder", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "web")))

    def test_other_languages_by_project(self):
        os.remove(os.path.join(self.proj, "main.c"))
        for name, lang in (("App.csproj", "C#"), ("pyproject.toml", "Python"), ("requirements.txt", "Python"), ("build.gradle", "Java"), ("Cargo.toml", "Rust"), ("go.mod", "Go"), ("build.zig", "Zig"), ("app-1.rockspec", "Lua"), ("package.json", "JavaScript"), ("project.godot", "Godot")):
            path = os.path.join(self.proj, name)
            with open(path, "w") as f:
                f.write("x")
            with self.assertRaises(SystemExit) as e:
                self.build("--goome", self.tree)
            self.assertIn(lang, str(e.exception))
            os.remove(path)

    def test_c_app_in_a_mixed_project_still_builds(self):
        with open(os.path.join(self.proj, "package.json"), "w") as f:
            f.write("{}")
        rc, _ = self.build("--goome", self.tree)
        self.assertEqual(rc, 0)

    def test_c_file_with_odd_extension_still_builds(self):
        with open(os.path.join(self.proj, "weird.cc"), "w") as f:
            f.write("x")
        rc, _ = self.build("weird.cc", "--goome", self.tree)
        self.assertEqual(rc, 0)

    def test_not_an_app_is_explained(self):
        with open(os.path.join(self.proj, "refuse.c"), "w") as f:
            f.write("x")
        with self.assertRaises(SystemExit) as e:
            self.build("refuse.c", "--goome", self.tree)
        self.assertIn("isnt a goome app", str(e.exception))
        self.assertNotIn("web-build:", str(e.exception))

    def test_no_clang(self):
        with mock.patch.dict(os.environ, {"CLANG": os.path.join(self.dir, "missing"), "PATH": self.bin + "-none"}):
            with self.assertRaises(SystemExit) as e:
                self.build("--goome", self.tree)
        self.assertIn("apt install clang lld", str(e.exception))

    def test_clang_without_wasm(self):
        script(os.path.join(self.bin, "clang"), 'echo "x86-64 - 64-bit X86"\n')
        with self.assertRaises(SystemExit) as e:
            self.build("--goome", self.tree)
        self.assertIn("cant target wasm32", str(e.exception))

    def test_no_wasm_ld(self):
        os.remove(os.path.join(self.bin, "wasm-ld"))
        with mock.patch.dict(os.environ, {"WASM_LD": "", "PATH": self.bin + "-none"}):
            with self.assertRaises(SystemExit) as e:
                self.build("--goome", self.tree)
        self.assertIn("wasm-ld", str(e.exception))

    def test_bad_checkout(self):
        with self.assertRaises(SystemExit) as e:
            self.build("--goome", self.dir)
        self.assertIn("isnt a c-goome checkout", str(e.exception))

    def tarball(self, with_web):
        path = os.path.join(self.dir, "dl.tar.gz")
        with tarfile.open(path, "w:gz") as tar:
            add(tar, "c-goome-x/src/goome.c")
            if with_web:
                add(tar, "c-goome-x/wasm/web-build.sh", STUB.encode(), 0o755)
        with open(path, "rb") as f:
            return f.read()

    def test_download(self):
        shutil.rmtree(self.tree)
        asked = []
        data = self.tarball(True)

        def fetch(url):
            asked.append(url)
            return data

        with mock.patch.object(goome, "fetch", fetch):
            rc, _ = self.build("--ref", "dev")
        self.assertEqual(rc, 0)
        self.assertEqual(asked, ["https://codeload.github.com/goome-ui/c-goome/tar.gz/dev"])

    def test_download_without_web(self):
        shutil.rmtree(self.tree)
        data = self.tarball(False)
        with mock.patch.object(goome, "fetch", lambda url: data):
            with self.assertRaises(SystemExit) as e:
                self.build("--ref", "main")
        self.assertIn("no web build yet", str(e.exception))

    def test_serve(self):
        site = os.path.join(self.dir, "site")
        os.makedirs(site)
        with open(os.path.join(site, "index.html"), "w") as f:
            f.write("<title>hi</title>")
        with open(os.path.join(site, "goome.wasm"), "wb") as f:
            f.write(b"\0asm")
        srv = goome.make_server(site, "127.0.0.1", 0)
        t = threading.Thread(target=srv.serve_forever)
        t.start()
        try:
            base = "http://127.0.0.1:%d/" % srv.server_address[1]
            with urllib.request.urlopen(base) as r:
                self.assertIn(b"hi", r.read())
            with urllib.request.urlopen(base + "goome.wasm") as r:
                self.assertEqual(r.headers["Content-Type"], "application/wasm")
        finally:
            srv.shutdown()
            t.join()
            srv.server_close()

    def test_serve_needs_a_build(self):
        with self.assertRaises(SystemExit):
            goome.make_server(self.dir, "127.0.0.1", 0)


@unittest.skipUnless(os.environ.get("GOOME_SRC") and shutil.which("bash"), "set GOOME_SRC to a c-goome checkout with clang and lld to run this")
class RealWeb(unittest.TestCase):
    def test_counter(self):
        try:
            goome.find_tools()
        except SystemExit as e:
            self.skipTest(str(e))
        d = tempfile.mkdtemp()
        try:
            out = os.path.join(d, "site")
            src = os.environ["GOOME_SRC"]
            with redirect_stdout(io.StringIO()):
                rc = goome.main(["build", "--web", os.path.join(src, "examples", "web_counter.c"), "--out", out, "--goome", src])
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(os.listdir(out)), ["goome.js", "goome.wasm", "index.html"])
            with open(os.path.join(out, "index.html")) as f:
                self.assertIn("<title>Counter</title>", f.read())
            with open(os.path.join(out, "goome.wasm"), "rb") as f:
                self.assertEqual(f.read(4), b"\0asm")
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
