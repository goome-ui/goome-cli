import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import goome

LATEST = "0.5.7"
REAL_ZIG_HASH = goome.zig_hash

PROJECTS = {
    "csharp": {"App.csproj": '<Project>\n  <ItemGroup>\n    <PackageReference Include="GoomeSharp" Version="0.5.5" />\n  </ItemGroup>\n</Project>\n'},
    "python": {"requirements.txt": "goome==0.5.5\n"},
    "java": {"gradle.properties": "goome_version=0.5.5\n", "build.gradle": 'dependencies { implementation "io.github.goome-ui:goome:$goome_version" }\n'},
    "rust": {"Cargo.toml": '[package]\nname = "x"\n\n[dependencies]\ngoome = "0.5.5"\n', "variants/hud/Cargo.toml": '[dependencies]\ngoome = "0.5.5"\n'},
    "node": {"package.json": '{"dependencies": {"goome": "https://github.com/goome-ui/node-goome/releases/download/v0.5.5/goome-0.5.5.tgz"}}\n'},
    "go": {"go.mod": "module x\n\nrequire github.com/goome-ui/go-goome v0.5.5\n"},
    "zig": {"build.zig.zon": '.{\n    .dependencies = .{\n        .goome = .{\n            .url = "https://github.com/goome-ui/zig-goome/archive/refs/tags/v0.5.5.tar.gz",\n            .hash = "goome-0.5.5-OLD",\n        },\n    },\n}\n'},
    "lua": {"goome-0.5.5-1.rockspec": 'package = "goome"\nversion = "0.5.5-1"\nsource = {\n  url = "git+https://github.com/goome-ui/lua-goome.git",\n  tag = "v0.5.5",\n}\n', "README.md": "luarocks install --local goome-0.5.5-1.rockspec\n"},
    "godot": {"get-goome.sh": 'v="${1:-${GOOME_VERSION:-0.5.5}}"\n', "get-goome.ps1": 'param([string]$Version = $(if ($env:GOOME_VERSION) { $env:GOOME_VERSION } else { "0.5.5" }))\n'},
    "c": {"goome.h": '#define GOOME_VERSION "0.5.5"\n'},
}

HEADER = '#define GOOME_VERSION "%s"\n#ifdef GOOME_IMPLEMENTATION\n#endif\n'


def release(tag):
    return json.dumps({"tag_name": tag}).encode()


def registry(latest=LATEST, missing=(), go_extra=""):
    pages = {
        "https://pypi.org/pypi/goome/json": json.dumps({"releases": {"0.5.5": [{"yanked": False}], latest: [{"yanked": False}], "0.9.0rc1": [{"yanked": False}], "0.9.9": [{"yanked": True}]}}).encode(),
        "https://api.nuget.org/v3-flatcontainer/goomesharp/index.json": json.dumps({"versions": ["0.5.5", latest, "0.9.0-beta"]}).encode(),
        "https://repo1.maven.org/maven2/io/github/goome-ui/goome/maven-metadata.xml": ("<metadata><versioning><versions><version>0.5.5</version><version>%s</version><version>0.9.0-rc1</version></versions></versioning></metadata>" % latest).encode(),
        "https://crates.io/api/v1/crates/goome": json.dumps({"crate": {"max_stable_version": latest}}).encode(),
        "https://proxy.golang.org/github.com/goome-ui/go-goome/@v/list": ("v0.5.5\nv%s\nv0.9.0-rc.1\n%s" % (latest, go_extra)).encode(),
        "https://github.com/goome-ui/c-goome/releases/download/v%s/goome.h" % latest: (HEADER % latest).encode(),
    }
    for repo in ("node-goome", "zig-goome", "lua-goome", "godot-goome", "c-goome"):
        pages["https://api.github.com/repos/goome-ui/%s/releases/latest" % repo] = release("v" + latest)

    def fake(url, timeout=60):
        if url in missing:
            raise OSError("no network")
        if url not in pages:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        return pages[url]
    return fake


class Upgrade(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp())
        self.patches = [mock.patch.object(goome, "fetch", registry()), mock.patch.object(goome, "zig_hash", lambda url: "goome-NEW")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir)

    def project(self, lang, sub=""):
        root = os.path.normpath(os.path.join(self.dir, sub))
        for name, text in PROJECTS[lang].items():
            path = os.path.join(root, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        return root

    def read(self, root, name):
        with open(os.path.join(root, name)) as f:
            return f.read()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = goome.main(["upgrade"] + list(args))
        return rc, out.getvalue(), err.getvalue()

    def test_check_every_language(self):
        for lang in PROJECTS:
            with self.subTest(lang=lang):
                root = self.project(lang, lang)
                before = {n: self.read(root, n) for n in PROJECTS[lang]}
                rc, out, _ = self.run_cli("--check", "--json", "--dir", root)
                info = json.loads(out)
                self.assertEqual(rc, 10)
                self.assertTrue(info["ok"])
                self.assertEqual((info["lang"], info["root"], info["current"], info["latest"], info["update"]), (lang, root, "0.5.5", LATEST, True))
                self.assertTrue(info["files"])
                self.assertNotIn("applied", info)
                self.assertEqual({n: self.read(root, n) for n in PROJECTS[lang]}, before)

    def test_next_commands(self):
        want = {"csharp": "dotnet restore", "python": "pip install -r requirements.txt", "java": "./gradlew build --refresh-dependencies", "rust": "cargo update -p goome", "node": "npm install", "go": "go mod tidy", "zig": "zig build", "lua": "luarocks make", "godot": "run get-goome.sh", "c": None}
        for lang, nxt in want.items():
            with self.subTest(lang=lang):
                root = self.project(lang, lang)
                _, out, _ = self.run_cli("--check", "--json", "--dir", root)
                self.assertEqual(json.loads(out)["next"], nxt)

    def test_apply_every_language_then_up_to_date(self):
        for lang in PROJECTS:
            with self.subTest(lang=lang):
                root = self.project(lang, lang)
                rc, out, _ = self.run_cli("--json", "--dir", root)
                info = json.loads(out)
                self.assertEqual(rc, 0)
                self.assertTrue(info["applied"])
                self.assertEqual(info["version"], LATEST)
                rc, out, _ = self.run_cli("--check", "--json", "--dir", root)
                again = json.loads(out)
                self.assertEqual(rc, 0)
                self.assertFalse(again["update"])
                self.assertEqual(again["current"], LATEST)
                self.assertEqual(again["files"], [])

    def test_csharp_edit(self):
        root = self.project("csharp")
        self.run_cli("--dir", root)
        self.assertIn('Include="GoomeSharp" Version="0.5.7"', self.read(root, "App.csproj"))

    def test_python_keeps_operator(self):
        root = self.project("python")
        with open(os.path.join(root, "requirements.txt"), "w") as f:
            f.write("requests\ngoome>=0.5.5\n")
        self.run_cli("--dir", root)
        self.assertEqual(self.read(root, "requirements.txt"), "requests\ngoome>=0.5.7\n")

    def test_python_pyproject(self):
        root = self.dir
        with open(os.path.join(root, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "app"\ndependencies = ["goome==0.5.5", "rich"]\n')
        self.run_cli("--dir", root)
        self.assertIn('"goome==0.5.7"', self.read(root, "pyproject.toml"))

    def test_python_name_alone_is_not_a_pin(self):
        with open(os.path.join(self.dir, "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "goome"\n')
        rc, _, err = self.run_cli("--dir", self.dir)
        self.assertEqual(rc, 2)

    def test_java_properties_and_literal(self):
        root = self.project("java")
        with open(os.path.join(root, "build.gradle"), "w") as f:
            f.write('implementation "io.github.goome-ui:goome:0.5.5"\n')
        self.run_cli("--dir", root)
        self.assertEqual(self.read(root, "gradle.properties"), "goome_version=0.5.7\n")
        self.assertIn("io.github.goome-ui:goome:0.5.7", self.read(root, "build.gradle"))

    def test_rust_variants_updated(self):
        root = self.project("rust")
        rc, out, _ = self.run_cli("--check", "--json", "--dir", root)
        self.assertEqual(sorted(json.loads(out)["files"]), ["Cargo.toml", "variants/hud/Cargo.toml"])
        self.run_cli("--dir", root)
        self.assertIn('goome = "0.5.7"', self.read(root, "Cargo.toml"))
        self.assertIn('goome = "0.5.7"', self.read(root, "variants/hud/Cargo.toml"))

    def test_rust_inline_table(self):
        root = self.dir
        with open(os.path.join(root, "Cargo.toml"), "w") as f:
            f.write('[dependencies]\ngoome = { version = "0.5.5", features = ["x"] }\ngoome-sys = "0.5.0"\n')
        self.run_cli("--dir", root)
        self.assertEqual(self.read(root, "Cargo.toml"), '[dependencies]\ngoome = { version = "0.5.7", features = ["x"] }\ngoome-sys = "0.5.0"\n')

    def test_node_both_spots(self):
        root = self.project("node")
        self.run_cli("--dir", root)
        self.assertIn("download/v0.5.7/goome-0.5.7.tgz", self.read(root, "package.json"))
        self.assertNotIn("0.5.5", self.read(root, "package.json"))

    def test_go_ignores_prerelease_and_sorts_numerically(self):
        with mock.patch.object(goome, "fetch", registry(latest="0.5.9", go_extra="v0.5.10\n")):
            root = self.project("go")
            _, out, _ = self.run_cli("--check", "--json", "--dir", root)
            self.assertEqual(json.loads(out)["latest"], "0.5.10")

    def test_zig_url_and_hash(self):
        root = self.project("zig")
        self.run_cli("--dir", root)
        text = self.read(root, "build.zig.zon")
        self.assertIn("refs/tags/v0.5.7.tar.gz", text)
        self.assertIn('.hash = "goome-NEW"', text)

    def test_zig_missing_leaves_file_and_exits_3(self):
        root = self.project("zig")
        before = self.read(root, "build.zig.zon")
        with mock.patch.object(goome, "zig_hash", REAL_ZIG_HASH), mock.patch.object(goome.shutil, "which", return_value=None):
            rc, out, _ = self.run_cli("--json", "--dir", root)
        self.assertEqual(rc, 3)
        self.assertFalse(json.loads(out)["ok"])
        self.assertIn("zig", json.loads(out)["error"])
        self.assertEqual(self.read(root, "build.zig.zon"), before)

    def test_zig_check_works_without_zig(self):
        root = self.project("zig")
        with mock.patch.object(goome, "zig_hash", REAL_ZIG_HASH), mock.patch.object(goome.shutil, "which", return_value=None):
            rc, _, _ = self.run_cli("--check", "--dir", root)
        self.assertEqual(rc, 10)

    def test_lua_renames_and_edits(self):
        root = self.project("lua")
        rc, out, _ = self.run_cli("--json", "--dir", root)
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(os.listdir(root)), ["README.md", "goome-0.5.7-1.rockspec"])
        text = self.read(root, "goome-0.5.7-1.rockspec")
        self.assertIn('version = "0.5.7-1"', text)
        self.assertIn('tag = "v0.5.7"', text)
        self.assertEqual(self.read(root, "README.md"), "luarocks install --local goome-0.5.7-1.rockspec\n")
        self.assertIn("goome-0.5.7-1.rockspec", json.loads(out)["files"])

    def test_godot_both_scripts(self):
        root = self.project("godot")
        self.run_cli("--dir", root)
        self.assertIn("GOOME_VERSION:-0.5.7}", self.read(root, "get-goome.sh"))
        self.assertIn('else { "0.5.7" }', self.read(root, "get-goome.ps1"))

    def test_c_downloads_the_header(self):
        root = self.project("c")
        self.run_cli("--dir", root)
        self.assertEqual(self.read(root, "goome.h"), HEADER % LATEST)

    def test_c_bad_header_left_alone(self):
        root = self.project("c")
        pages = registry()
        wrong = "https://github.com/goome-ui/c-goome/releases/download/v%s/goome.h" % LATEST

        def fake(url, timeout=60):
            return b"junk" if url == wrong else pages(url, timeout)
        with mock.patch.object(goome, "fetch", fake):
            rc, _, _ = self.run_cli("--dir", root)
        self.assertEqual(rc, 3)
        self.assertEqual(self.read(root, "goome.h"), PROJECTS["c"]["goome.h"])

    def test_never_downgrades(self):
        root = self.project("python")
        with open(os.path.join(root, "requirements.txt"), "w") as f:
            f.write("goome==0.9.0\n")
        rc, out, _ = self.run_cli("--json", "--dir", root)
        info = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertFalse(info["update"])
        self.assertEqual(self.read(root, "requirements.txt"), "goome==0.9.0\n")

    def test_prerelease_pin_is_reported_and_left_alone(self):
        root = self.project("python")
        with open(os.path.join(root, "requirements.txt"), "w") as f:
            f.write("goome==0.6.0rc1\n")
        rc, out, _ = self.run_cli("--json", "--dir", root)
        info = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(info["current"], "0.6.0rc1")
        self.assertFalse(info["update"])
        self.assertIn("note", info)
        self.assertEqual(self.read(root, "requirements.txt"), "goome==0.6.0rc1\n")

    def test_only_the_stale_pin_moves(self):
        root = self.project("java")
        with open(os.path.join(root, "build.gradle"), "w") as f:
            f.write('implementation "io.github.goome-ui:goome:0.9.0"\n')
        self.run_cli("--dir", root)
        self.assertEqual(self.read(root, "gradle.properties"), "goome_version=0.5.7\n")
        self.assertIn("goome:0.9.0", self.read(root, "build.gradle"))

    def test_up_to_date_exit_zero(self):
        root = self.project("go")
        with open(os.path.join(root, "go.mod"), "w") as f:
            f.write("require github.com/goome-ui/go-goome v0.5.7\n")
        rc, out, _ = self.run_cli("--check", "--dir", root)
        self.assertEqual(rc, 0)
        self.assertIn("newest", out)

    def test_not_a_project(self):
        rc, out, err = self.run_cli("--json", "--dir", self.dir)
        self.assertEqual(rc, 2)
        self.assertFalse(json.loads(out)["ok"])
        rc, out, err = self.run_cli("--dir", self.dir)
        self.assertEqual(rc, 2)
        self.assertTrue(err.startswith("goome: "))
        self.assertEqual(out, "")

    def test_missing_dir(self):
        rc, _, _ = self.run_cli("--json", "--dir", os.path.join(self.dir, "nope"))
        self.assertEqual(rc, 2)

    def test_registry_unreachable(self):
        root = self.project("python")
        with mock.patch.object(goome, "fetch", registry(missing=("https://pypi.org/pypi/goome/json",))):
            rc, out, _ = self.run_cli("--json", "--dir", root)
        self.assertEqual(rc, 4)
        self.assertFalse(json.loads(out)["ok"])
        self.assertEqual(self.read(root, "requirements.txt"), "goome==0.5.5\n")

    def test_walks_up_to_the_root(self):
        root = self.project("python")
        deep = os.path.join(root, "src", "pkg")
        os.makedirs(deep)
        rc, out, _ = self.run_cli("--check", "--json", "--dir", deep)
        self.assertEqual(json.loads(out)["root"], root)

    def test_default_dir_is_cwd(self):
        root = self.project("python")
        here = os.getcwd()
        os.chdir(root)
        try:
            rc, out, _ = self.run_cli("--check", "--json")
        finally:
            os.chdir(here)
        self.assertEqual(json.loads(out)["root"], root)

    def test_never_leaves_the_root(self):
        outer = self.project("python")
        inner = os.path.join(outer, "app")
        os.makedirs(inner)
        with open(os.path.join(inner, "go.mod"), "w") as f:
            f.write("require github.com/goome-ui/go-goome v0.5.5\n")
        self.run_cli("--dir", inner)
        self.assertEqual(self.read(outer, "requirements.txt"), "goome==0.5.5\n")
        self.assertIn("v0.5.7", self.read(inner, "go.mod"))

    def test_symlinked_pin_is_not_followed(self):
        root = self.project("python")
        elsewhere = tempfile.mkdtemp()
        try:
            target = os.path.join(elsewhere, "requirements.txt")
            with open(target, "w") as f:
                f.write("goome==0.5.5\n")
            os.remove(os.path.join(root, "requirements.txt"))
            os.symlink(target, os.path.join(root, "requirements.txt"))
            rc, _, _ = self.run_cli("--dir", root)
            self.assertEqual(rc, 2)
            with open(target) as f:
                self.assertEqual(f.read(), "goome==0.5.5\n")
        finally:
            shutil.rmtree(elsewhere)

    def test_human_output(self):
        root = self.project("csharp")
        rc, out, _ = self.run_cli("--check", "--dir", root)
        self.assertEqual(rc, 10)
        self.assertTrue(out.startswith("goome: csharp project"))
        self.assertIn("goome upgrade", out)
        rc, out, _ = self.run_cli("--dir", root)
        self.assertEqual(rc, 0)
        self.assertIn("0.5.5 -> 0.5.7", out)
        self.assertIn("next: dotnet restore", out)

    def test_json_is_one_object(self):
        root = self.project("rust")
        _, out, _ = self.run_cli("--json", "--dir", root)
        self.assertEqual(len(out.strip().splitlines()), 1)
        info = json.loads(out)
        for key in ("ok", "lang", "root", "current", "latest", "update", "files", "next", "applied", "version"):
            self.assertIn(key, info)


if __name__ == "__main__":
    unittest.main()
