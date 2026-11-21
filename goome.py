#!/usr/bin/env python3
import argparse
import functools
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

__version__ = "0.5.5"

ORG = "goome-ui"
PYPI_URL = "https://pypi.org/pypi/goome-cli/json"
RELEASES_URL = "https://api.github.com/repos/goome-ui/goome-cli/releases/latest"
ASSET_URL = "https://github.com/goome-ui/goome-cli/releases/latest/download/goome.py"
LANGS = {
    "c": "C, one goome.h, builds with any C compiler",
    "csharp": "C#, .NET 8 or newer",
    "python": "Python 3.8 or newer",
    "java": "Java 22 or newer, Gradle",
    "godot": "Godot 4.4 or newer, GDScript",
    "rust": "Rust 1.77 or newer, cargo",
    "node": "Node 18 or newer, npm",
    "go": "Go 1.23 or newer, cgo with a C compiler",
    "zig": "Zig 0.15.2",
    "lua": "Lua 5.4 or LuaJIT, LuaRocks and a C compiler",
}
TEMPLATES = {
    "app": "a normal window, with a toggle that turns it into an overlay",
    "overlay": "a see-through overlay, only the window takes clicks",
    "mod-menu": "a menu over the game that a hotkey opens and closes",
    "hud": "a little info panel in the corner, clicks go through it",
}
TEMPLATE_ONLY = ["variants", "tests", "CONTRIBUTING.md", ".github/workflows/pr-rules.yml", ".github/update-goome.sh", ".github/workflows/update-goome.yml"]
TOKENS = ("My Goome App", "my-goome-app", "my_goome_app", "MyGoomeApp", "mygoomeapp")


def names(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    if not words:
        raise SystemExit("goome: %r isnt a usable name, use letters and numbers" % name)
    lower = [w.lower() for w in words]
    pascal = "".join(w[:1].upper() + w[1:] for w in words)
    flat = "".join(lower)
    if pascal[0].isdigit():
        pascal = "App" + pascal
    if flat[0].isdigit():
        flat = "app" + flat
    title = " ".join(w[:1].upper() + w[1:] for w in words)
    return dict(zip(TOKENS, (title, "-".join(lower), "_".join(lower), pascal, flat)))


def rockspec_in(root):
    if root and os.path.isdir(root):
        found = sorted(f for f in os.listdir(root) if f.endswith(".rockspec"))
        if found:
            return found[-1]
    return None


def next_steps(lang, folder, kebab, root=None):
    cd = "cd " + (folder if " " not in folder else '"%s"' % folder)
    spec = rockspec_in(root)
    steps = {
        "c": [cd, "cc -O2 -o %s main.c goome.c" % kebab, "./" + kebab, "",
              "or with cmake (windows too):", "cmake -S . -B build", "cmake --build build"],
        "csharp": [cd, "dotnet run"],
        "python": [cd, "python -m venv .venv", "source .venv/bin/activate   (.venv\\Scripts\\activate on windows)",
                   "pip install -r requirements.txt", "python main.py"],
        "java": [cd, "./gradlew run   (gradlew.bat run on windows)"],
        "godot": [cd, "./get-goome.sh   (or get-goome.ps1 on windows)", "godot -e --path ."],
        "rust": [cd, "cargo run"],
        "node": [cd, "npm install", "node main.js"],
        "go": [cd, "go run ."],
        "zig": [cd, "zig build run"],
        "lua": [cd, "luarocks install --local " + spec if spec else "luarocks make --local",
                "eval \"$(luarocks path)\"   (on windows run luarocks path and do what it prints)", "lua main.lua"],
    }
    return steps[lang]


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "goome-cli/" + __version__})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(lang, ref):
    repo = "%s/goome-app-template-%s" % (ORG, lang)
    if ref:
        tries = [ref]
    else:
        tries = ["refs/tags/v" + __version__, "refs/heads/main"]
    for i, r in enumerate(tries):
        url = "https://codeload.github.com/%s/tar.gz/%s" % (repo, r)
        try:
            return fetch(url), r
        except urllib.error.HTTPError as e:
            if e.code != 404 or i == len(tries) - 1:
                raise SystemExit("goome: couldnt download %s (%s)" % (url, e))
        except urllib.error.URLError as e:
            raise SystemExit("goome: couldnt reach github: %s" % e.reason)


def safe_extract(data, dest):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        root = os.path.realpath(dest)
        for m in tar.getmembers():
            if not (m.isfile() or m.isdir()):
                continue
            parts = m.name.replace("\\", "/").split("/")[1:]
            if not parts or not parts[0] or ".." in parts or m.name.startswith("/"):
                continue
            out = os.path.realpath(os.path.join(root, *parts))
            if not out.startswith(root + os.sep):
                continue
            if m.isdir():
                os.makedirs(out, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(out), exist_ok=True)
            src = tar.extractfile(m)
            with open(out, "wb") as f:
                shutil.copyfileobj(src, f)
            if m.mode & 0o111:
                os.chmod(out, 0o755)


def copy_local(src, dest):
    skip = {".git", ".venv", "build", "bin", "obj", ".gradle", ".godot", "__pycache__", "target", "node_modules", ".zig-cache", "zig-out", "lua_modules"}
    for top, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip]
        rel = os.path.relpath(top, src)
        os.makedirs(os.path.join(dest, rel), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(top, f), os.path.join(dest, rel, f))


def apply_variant(dest, template):
    if template == "app":
        return
    var = os.path.join(dest, "variants", template)
    if not os.path.isdir(var):
        raise SystemExit("goome: this template doesnt have a %s version" % template)
    for top, dirs, files in os.walk(var):
        rel = os.path.relpath(top, var)
        os.makedirs(os.path.join(dest, rel), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(top, f), os.path.join(dest, rel, f))


def strip_template(dest):
    for p in TEMPLATE_ONLY:
        full = os.path.join(dest, *p.split("/"))
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.exists(full):
            os.remove(full)


def rename(dest, table):
    for top, dirs, files in os.walk(dest):
        for f in files:
            path = os.path.join(top, f)
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                text = raw.decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new = text
            for old, value in table.items():
                new = new.replace(old, value)
            if new != text:
                with open(path, "wb") as fh:
                    fh.write(new.encode("utf-8"))
    for top, dirs, files in os.walk(dest, topdown=False):
        for f in dirs + files:
            new = f
            for old, value in table.items():
                new = new.replace(old, value)
            if new != f:
                os.rename(os.path.join(top, f), os.path.join(top, new))


def write_readme(dest, lang, template, table):
    title = table["My Goome App"]
    lines = ["# " + title, "",
             "Made with [goome](https://goome.wtf/docs/), from the %s %s template." % (lang, template), "",
             "```sh"] + [s for s in next_steps(lang, ".", table["my-goome-app"], dest)[1:] if s and not s.endswith(":")] + ["```", ""]
    with open(os.path.join(dest, "README.md"), "w") as f:
        f.write("\n".join(lines))


def cmd_new(a):
    folder = a.dir or a.name
    dest = os.path.abspath(folder)
    if os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest)):
        raise SystemExit("goome: %s already exists and isnt empty" % folder)
    table = names(a.name)
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    work = tempfile.mkdtemp(prefix=".goome-new-", dir=parent)
    try:
        if a.source:
            if os.path.isdir(a.source):
                copy_local(a.source, work)
            else:
                with open(a.source, "rb") as f:
                    safe_extract(f.read(), work)
            got = a.source
        else:
            data, got = download(a.lang, a.ref)
            safe_extract(data, work)
        apply_variant(work, a.template)
        strip_template(work)
        rename(work, table)
        write_readme(work, a.lang, a.template, table)
        if os.path.isdir(dest):
            os.rmdir(dest)
        os.rename(work, dest)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    print("made %s (%s, %s template, from %s)" % (folder, a.lang, a.template, got))
    print("")
    print("next:")
    for s in next_steps(a.lang, folder, table["my-goome-app"], dest):
        print("  " + s if s else "")
    return 0


def cmd_list(a):
    print("languages (--lang):")
    for k, v in LANGS.items():
        print("  %-9s %s" % (k, v))
    print("")
    print("templates (--template):")
    for k, v in TEMPLATES.items():
        print("  %-9s %s" % (k, v))
    print("")
    print("template repos: https://github.com/%s/goome-app-template-<lang>" % ORG)
    return 0


CLANGS = ["clang"] + ["clang-%d" % v for v in range(25, 13, -1)]
LLVM_DIRS = ["/opt/homebrew/opt/llvm/bin", "/usr/local/opt/llvm/bin", "/usr/lib/llvm/bin", "C:\\Program Files\\LLVM\\bin"]
INSTALL_HINT = (
    "install clang and lld with the webassembly target:\n"
    "  debian/ubuntu  sudo apt install clang lld\n"
    "  fedora         sudo dnf install clang lld\n"
    "  arch           sudo pacman -S clang lld\n"
    "  mac            brew install llvm lld   (apples own clang cant do wasm)\n"
    "  windows        winget install LLVM.LLVM\n"
    "or point CLANG and WASM_LD at ones you have"
)


def which_in(name, extra=()):
    found = shutil.which(name)
    if found:
        return found
    for d in extra:
        for ext in ("", ".exe"):
            p = os.path.join(d, name + ext)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def can_wasm(clang):
    try:
        r = subprocess.run([clang, "--print-targets"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return "wasm32" in r.stdout


def find_tools():
    want = os.environ.get("CLANG")
    names = [want] if want else CLANGS
    clang = None
    seen = False
    for n in names:
        c = which_in(n, LLVM_DIRS)
        if not c:
            continue
        seen = True
        if can_wasm(c):
            clang = c
            break
    if not clang:
        if seen:
            raise SystemExit("goome: found clang but it cant target wasm32.\n" + INSTALL_HINT)
        raise SystemExit("goome: no clang found, building for the web needs one.\n" + INSTALL_HINT)
    ld = os.environ.get("WASM_LD")
    if ld and not os.path.isfile(ld):
        ld = which_in(ld, LLVM_DIRS)
    if not ld:
        beside = os.path.join(os.path.dirname(os.path.realpath(clang)), "wasm-ld")
        ld = beside if os.path.isfile(beside) else which_in("wasm-ld", LLVM_DIRS)
    if not ld:
        raise SystemExit("goome: no wasm-ld found, its in the lld package.\n" + INSTALL_HINT)
    return clang, ld


def is_goome_tree(d):
    return os.path.isfile(os.path.join(d, "wasm", "web-build.sh")) and os.path.isfile(os.path.join(d, "src", "goome.c"))


def cache_dir():
    home = os.path.expanduser("~")
    base = os.environ.get("XDG_CACHE_HOME")
    if not base and os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    if not base and sys.platform == "darwin":
        base = os.path.join(home, "Library", "Caches")
    base = base or os.path.join(home, ".cache")
    return os.path.join(base, "goome")


def find_source(app, given, ref):
    if given:
        if not is_goome_tree(given):
            raise SystemExit("goome: %s isnt a c-goome checkout (no wasm/web-build.sh), use a newer one" % given)
        return given
    env = os.environ.get("GOOME_SRC")
    if env:
        if not is_goome_tree(env):
            raise SystemExit("goome: GOOME_SRC=%s isnt a c-goome checkout with wasm/web-build.sh" % env)
        return env
    here = os.path.dirname(os.path.abspath(app))
    for start in (here, os.getcwd()):
        d = start
        while True:
            for cand in (d, os.path.join(d, "c-goome"), os.path.join(d, "goome"), os.path.join(d, "vendor", "c-goome")):
                if is_goome_tree(cand):
                    return cand
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    tries = [ref] if ref else ["refs/tags/v" + __version__, "refs/heads/main"]
    last = None
    for i, r in enumerate(tries):
        dest = os.path.join(cache_dir(), "c-goome-" + r.replace("/", "-"))
        if is_goome_tree(dest) and r.startswith("refs/tags/"):
            return dest
        url = "https://codeload.github.com/%s/c-goome/tar.gz/%s" % (ORG, r)
        try:
            data = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise SystemExit("goome: couldnt download %s (%s)" % (url, e))
            continue
        except urllib.error.URLError as e:
            raise SystemExit("goome: couldnt reach github: %s" % e.reason)
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        safe_extract(data, dest)
        if is_goome_tree(dest):
            return dest
        last = r
        shutil.rmtree(dest, ignore_errors=True)
    if last:
        raise SystemExit("goome: %s of c-goome has no web build yet. use --ref dev or --goome <checkout of c-goome>" % last.split("/")[-1])
    raise SystemExit("goome: couldnt find c-goome %s, use --goome <checkout of c-goome>" % (ref or "v" + __version__))


LANG_EXT = {".cs": "C#", ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".rs": "Rust", ".go": "Go", ".zig": "Zig", ".lua": "Lua", ".js": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript", ".gd": "GDScript"}
LANG_FILES = (
    ("project.godot", "Godot"), ("Cargo.toml", "Rust"), ("go.mod", "Go"), ("build.zig", "Zig"),
    ("pyproject.toml", "Python"), ("requirements.txt", "Python"), ("build.gradle", "Java"),
    ("build.gradle.kts", "Kotlin"), ("pom.xml", "Java"), ("package.json", "JavaScript"),
)
WEB_HINT = "try it live at https://goome.wtf/builder/ or see https://goome.wtf/docs/browser/"


def not_c(lang):
    return SystemExit(
        "goome: building for the web only works for C apps right now, this looks like a %s project. "
        "the web build compiles C, so the same app needs to be written in C to go in the browser. %s" % (lang, WEB_HINT))


def other_language(path):
    if path:
        return LANG_EXT.get(os.path.splitext(path)[1].lower())
    try:
        names = os.listdir(".")
    except OSError:
        return None
    for n in names:
        if n.endswith((".csproj", ".sln", ".rockspec")):
            return "C#" if not n.endswith(".rockspec") else "Lua"
    for f, lang in LANG_FILES:
        if f in names:
            return lang
    return None


def find_app(path):
    if path:
        if not os.path.isfile(path):
            raise SystemExit("goome: no such file: %s" % path)
        return path
    for c in ("main.c", os.path.join("src", "main.c"), "app.c", os.path.join("src", "app.c")):
        if os.path.isfile(c):
            return c
    raise SystemExit("goome: which file? give it as goome build --web app.c (looked for main.c, src/main.c, app.c)")


def cmd_build(a):
    if not a.web:
        raise SystemExit("goome: build needs a target, only --web so far")
    lang = other_language(a.file)
    if lang and (a.file or not any(os.path.isfile(c) for c in ("main.c", os.path.join("src", "main.c"), "app.c", os.path.join("src", "app.c")))):
        raise not_c(lang)
    app = find_app(a.file)
    clang, ld = find_tools()
    src = find_source(app, a.goome, a.ref)
    bash = shutil.which("bash")
    if not bash:
        raise SystemExit("goome: building for the web needs bash (git bash or wsl on windows)")
    out = os.path.abspath(a.out)
    env = dict(os.environ, CLANG=clang, WASM_LD=ld)
    cmd = [bash, os.path.join(src, "wasm", "web-build.sh"), app, out] + list(a.more)
    r = subprocess.run(cmd, env=env, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    if r.returncode:
        msg = r.stderr.strip() or r.stdout.strip() or "the build failed"
        if msg.startswith("web-build: "):
            msg = msg[len("web-build: "):]
        raise SystemExit("goome: " + msg)
    print(r.stdout.strip())
    print("")
    print("serve it with: goome serve %s" % a.out)
    return 0


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{".wasm": "application/wasm", ".js": "text/javascript"})

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def make_server(folder, bind, port):
    if not os.path.isfile(os.path.join(folder, "index.html")):
        raise SystemExit("goome: no index.html in %s, build it first with goome build --web" % folder)
    handler = functools.partial(Quiet, directory=os.path.abspath(folder))
    try:
        return http.server.ThreadingHTTPServer((bind, port), handler)
    except OSError as e:
        raise SystemExit("goome: cant listen on %s:%d (%s)" % (bind, port, e.strerror))


def cmd_serve(a):
    srv = make_server(a.dir, a.bind, a.port)
    print("serving %s at http://%s:%d/  (ctrl+c to stop)" % (a.dir, "localhost" if a.bind in ("127.0.0.1", "0.0.0.0") else a.bind, srv.server_address[1]))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        srv.server_close()
    return 0


def parse_version(text):
    parts = []
    for piece in str(text).strip().lstrip("vV").split("."):
        m = re.match(r"\d+", piece)
        if not m:
            break
        parts.append(int(m.group()))
    return tuple(parts)


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a) and a > b


def installed_with_pip():
    return os.path.basename(os.path.abspath(__file__)) == "goome_cli.py"


def latest_version(timeout=60):
    sources = [(PYPI_URL, lambda d: d["info"]["version"]), (RELEASES_URL, lambda d: d["tag_name"])]
    if not installed_with_pip():
        sources.reverse()
    for url, pick in sources:
        try:
            found = str(pick(json.loads(fetch(url, timeout).decode("utf-8")))).lstrip("vV")
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if parse_version(found):
            return found
    return None


def pip_upgrade_command():
    if os.sep + "pipx" + os.sep in sys.prefix.replace("\\", os.sep) and shutil.which("pipx"):
        return ["pipx", "upgrade", "goome-cli"]
    return [sys.executable, "-m", "pip", "install", "-U", "goome-cli"]


def replace_self(path, data):
    folder = os.path.dirname(path)
    if not os.access(folder, os.W_OK) or not os.access(path, os.W_OK):
        raise SystemExit("goome: cant write to %s, so it wasnt updated. Run the update with the rights that file needs, or download goome.py again by hand." % path)
    if hasattr(os, "geteuid") and os.stat(path).st_uid != os.geteuid():
        raise SystemExit("goome: %s belongs to another user (a system install?), so it wasnt updated. Update it the way it was installed." % path)
    shutil.copy2(path, path + ".bak")
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".goome-update-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def cmd_update(a):
    latest = latest_version(15)
    if not latest:
        print("goome: couldnt reach PyPI or GitHub to look for a new version", file=sys.stderr)
        return 1
    if a.check:
        print(latest)
        return 0
    if not is_newer(latest, __version__):
        print("goome %s is the newest" % __version__)
        return 0
    print("goome %s -> %s" % (__version__, latest))
    if installed_with_pip():
        cmd = pip_upgrade_command()
        print(" ".join(cmd))
        return subprocess.call(cmd)
    path = os.path.realpath(os.path.abspath(__file__))
    try:
        data = fetch(ASSET_URL, 60)
    except OSError as e:
        print("goome: couldnt download goome.py (%s)" % e, file=sys.stderr)
        return 1
    if ('__version__ = "%s"' % latest).encode() not in data:
        print("goome: the downloaded goome.py isnt version %s, not replacing anything" % latest, file=sys.stderr)
        return 1
    try:
        compile(data, "goome.py", "exec")
    except (SyntaxError, ValueError):
        print("goome: the downloaded goome.py is broken, not replacing anything", file=sys.stderr)
        return 1
    replace_self(path, data)
    print("updated %s, the old one is next to it as goome.py.bak" % path)
    return 0


def update_note():
    if os.environ.get("GOOME_NO_UPDATE_CHECK") or not sys.stdout.isatty():
        return
    try:
        stamp = os.path.join(cache_dir(), "update-check")
        try:
            with open(stamp) as f:
                last = float(f.read().strip())
        except (OSError, ValueError):
            last = 0
        now = time.time()
        if 0 <= now - last < 86400:
            return
        os.makedirs(cache_dir(), exist_ok=True)
        with open(stamp, "w") as f:
            f.write(str(now))
        latest = latest_version(2)
        if latest and is_newer(latest, __version__):
            print("goome %s is out (you have %s), run goome update" % (latest, __version__), file=sys.stderr)
    except Exception:
        return


def main(argv=None):
    p = argparse.ArgumentParser(prog="goome", description="makes a new goome project from a template, builds apps for the web")
    p.add_argument("--version", action="version", version="goome " + __version__)
    sub = p.add_subparsers(dest="cmd")
    n = sub.add_parser("new", help="make a new project")
    n.add_argument("name")
    n.add_argument("--lang", required=True, choices=list(LANGS))
    n.add_argument("--template", default="app", choices=list(TEMPLATES))
    n.add_argument("--dir", help="folder to make it in, the name by default")
    n.add_argument("--ref", help="branch, tag or commit of the template repo")
    n.add_argument("--from", dest="source", help="use a local template folder or .tar.gz instead of downloading")
    b = sub.add_parser("build", help="build your app, --web makes a folder you can host")
    b.add_argument("file", nargs="?", help="the app, main.c by default")
    b.add_argument("--web", action="store_true", help="compile it to webassembly with a page around it")
    b.add_argument("--out", default="web", help="folder to put it in, web by default")
    b.add_argument("--goome", help="a c-goome checkout to build with instead of downloading one")
    b.add_argument("--ref", help="branch or tag of c-goome to download")
    b.add_argument("--more", nargs="*", default=[], help="more .c files that belong to the app")
    sv = sub.add_parser("serve", help="host a folder you built with --web on localhost")
    sv.add_argument("dir", nargs="?", default="web")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--bind", default="127.0.0.1")
    sub.add_parser("list", help="show the languages and templates")
    u = sub.add_parser("update", help="update goome-cli to the newest version")
    u.add_argument("--check", action="store_true", help="only print the newest version")
    a = p.parse_args(argv)
    cmds = {"new": cmd_new, "build": cmd_build, "serve": cmd_serve, "list": cmd_list, "update": cmd_update}
    if a.cmd not in cmds:
        p.print_help()
        return 1
    code = cmds[a.cmd](a)
    if a.cmd in ("new", "build", "list"):
        update_note()
    return code


if __name__ == "__main__":
    sys.exit(main())
