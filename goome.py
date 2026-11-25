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

__version__ = "0.5.7"

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


def is_mine(d):
    if not hasattr(os, "geteuid"):
        return True
    return os.stat(os.path.join(d, "wasm", "web-build.sh")).st_uid in (0, os.geteuid())


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
                if is_goome_tree(cand) and is_mine(cand):
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


STABLE = re.compile(r"^\d+\.\d+\.\d+$")
SCAN_SKIP = {"node_modules", "target", "build", "bin", "obj", "lua_modules", "zig-out", "vendor", "dist", "out"}
MAX_PIN_FILE = 8 * 1024 * 1024


class UpgradeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def is_stable(version):
    return bool(STABLE.fullmatch(version))


def highest_stable(versions, where):
    found = [v for v in versions if is_stable(v)]
    if not found:
        raise UpgradeError(4, "%s has no stable goome version" % where)
    return max(found, key=parse_version)


def get_text(url):
    try:
        return fetch(url, 30).decode("utf-8")
    except (OSError, ValueError) as e:
        raise UpgradeError(4, "couldnt reach %s (%s)" % (url, getattr(e, "reason", None) or e))


def get_json(url):
    try:
        return json.loads(get_text(url))
    except ValueError:
        raise UpgradeError(4, "%s didnt send json" % url)


def latest_pypi():
    releases = get_json("https://pypi.org/pypi/goome/json").get("releases", {})
    live = [v for v, files in releases.items() if any(not f.get("yanked") for f in files)]
    return highest_stable(live, "pypi")


def latest_nuget():
    return highest_stable(get_json("https://api.nuget.org/v3-flatcontainer/goomesharp/index.json").get("versions", []), "nuget")


def latest_maven():
    xml = get_text("https://repo1.maven.org/maven2/io/github/goome-ui/goome/maven-metadata.xml")
    return highest_stable(re.findall(r"<version>([^<]+)</version>", xml), "maven central")


def latest_crate():
    found = get_json("https://crates.io/api/v1/crates/goome").get("crate", {}).get("max_stable_version")
    return highest_stable([str(found or "")], "crates.io")


def latest_go():
    listing = get_text("https://proxy.golang.org/github.com/goome-ui/go-goome/@v/list")
    return highest_stable([line.strip().lstrip("v") for line in listing.splitlines()], "the go proxy")


def latest_release(repo):
    def pick():
        tag = get_json("https://api.github.com/repos/%s/%s/releases/latest" % (ORG, repo)).get("tag_name", "")
        return highest_stable([str(tag).lstrip("vV")], "github %s" % repo)
    return pick


def swap_version(pattern, text, new):
    def one(m):
        start = m.start("v") - m.start()
        end = m.end("v") - m.start()
        return m.group(0)[:start] + new + m.group(0)[end:]
    return re.sub(pattern, one, text, flags=re.M)


def swap_all(patterns):
    def rewrite(text, new):
        for pattern in patterns:
            text = swap_version(pattern, text, new)
        return text
    return rewrite


class Pin:
    def __init__(self, path, version, text):
        self.path = path
        self.version = version
        self.text = text


class Kind:
    def __init__(self, name, wanted, patterns, nxt, latest):
        self.name = name
        self.wanted = wanted
        self.patterns = patterns
        self.next = nxt
        self.latest = latest

    def read(self, path):
        try:
            if os.path.islink(path) or os.path.getsize(path) > MAX_PIN_FILE:
                return None
            with open(path, "rb") as f:
                text = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        for pattern in self.patterns:
            m = re.search(pattern, text, re.M)
            if m:
                return Pin(path, m.group("v"), text)
        return None

    def changes(self, root, pin, new, dry):
        return [(pin.path, None, None if dry else swap_all(self.patterns)(pin.text, new))]


class NodeKind(Kind):
    def changes(self, root, pin, new, dry):
        text = None
        if not dry:
            text = re.sub(r'(node-goome/releases/download/v)[^/"]+(/goome-)[^"/]+?(\.tgz)', lambda m: m.group(1) + new + m.group(2) + new + m.group(3), pin.text)
        return [(pin.path, None, text)]


def zig_hash(url):
    zig = shutil.which("zig")
    if not zig:
        raise UpgradeError(3, "zig isnt installed, and the new hash in build.zig.zon comes from zig fetch. install zig 0.15.2 (https://ziglang.org/download/) and run goome upgrade again, build.zig.zon was left alone")
    try:
        r = subprocess.run([zig, "fetch", url], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise UpgradeError(3, "zig fetch didnt run (%s), build.zig.zon was left alone" % e)
    lines = r.stdout.strip().splitlines()
    if r.returncode or not lines:
        raise UpgradeError(3, "zig fetch failed: %s" % (r.stderr.strip() or "no hash came back"))
    return lines[-1].strip()


class ZigKind(Kind):
    def changes(self, root, pin, new, dry):
        if dry:
            return [(pin.path, None, None)]
        url = "https://github.com/goome-ui/zig-goome/archive/refs/tags/v%s.tar.gz" % new
        digest = zig_hash(url)
        text = swap_all(self.patterns)(pin.text, new)
        text, count = re.subn(r'(\.goome\s*=\s*\.\{[^}]*?\.hash\s*=\s*")[^"]*(")', lambda m: m.group(1) + digest + m.group(2), text, count=1, flags=re.S)
        if not count:
            raise UpgradeError(3, "found the goome url in build.zig.zon but not its .hash, left it alone")
        return [(pin.path, None, text)]


class LuaKind(Kind):
    def read(self, path):
        m = re.match(r"^goome-(\d[^-]*)-\d+\.rockspec$", os.path.basename(path))
        if not m or os.path.islink(path):
            return None
        try:
            with open(path, "rb") as f:
                return Pin(path, m.group(1), f.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError):
            return None

    def changes(self, root, pin, new, dry):
        folder = os.path.dirname(pin.path)
        old_name = os.path.basename(pin.path)
        new_name = "goome-%s-1.rockspec" % new
        text = pin.text
        if not dry:
            text = re.sub(r'^(version\s*=\s*")[^"]*(")', lambda m: m.group(1) + new + "-1" + m.group(2), text, flags=re.M)
            text = re.sub(r'^(\s*tag\s*=\s*")[^"]*(")', lambda m: m.group(1) + "v" + new + m.group(2), text, flags=re.M)
        done = [(pin.path, os.path.join(folder, new_name), None if dry else text)]
        readme = os.path.join(folder, "README.md")
        if os.path.isfile(readme) and not os.path.islink(readme):
            try:
                with open(readme, "rb") as f:
                    raw = f.read().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                raw = ""
            if old_name in raw:
                done.append((readme, None, None if dry else raw.replace(old_name, new_name)))
        return done


class CKind(Kind):
    def changes(self, root, pin, new, dry):
        if dry:
            return [(pin.path, None, None)]
        url = "https://github.com/goome-ui/c-goome/releases/download/v%s/goome.h" % new
        try:
            data = fetch(url, 120)
        except urllib.error.HTTPError as e:
            raise UpgradeError(3 if e.code == 404 else 4, "couldnt download %s (%s)" % (url, e))
        except OSError as e:
            raise UpgradeError(4, "couldnt download %s (%s)" % (url, e))
        text = data.decode("utf-8", "replace")
        if '#define GOOME_VERSION "%s"' % new not in text or "GOOME_IMPLEMENTATION" not in text:
            raise UpgradeError(3, "the goome.h that came from v%s isnt the right file, left yours alone" % new)
        return [(pin.path, None, text)]


def names_in(*files):
    return lambda name: name in files


KINDS = [
    Kind("csharp", lambda n: n.endswith(".csproj") or n == "Directory.Packages.props", [
        r'<Package(?:Reference|Version)\b[^>]*?\bInclude="GoomeSharp"[^>]*?\bVersion="(?P<v>[^"]+)"',
        r'<Package(?:Reference|Version)\b[^>]*?\bVersion="(?P<v>[^"]+)"[^>]*?\bInclude="GoomeSharp"',
        r'<Package(?:Reference|Version)\b[^>]*?\bInclude="GoomeSharp"[^>]*>\s*<Version>(?P<v>[^<]+)</Version>',
    ], "dotnet restore", latest_nuget),
    Kind("python", names_in("requirements.txt", "pyproject.toml"), [
        r'^[ \t]*goome(?:\[[^\]]*\])?[ \t]*(?:===|==|~=|>=|<=)[ \t]*(?P<v>\d[^\s,;#"\']*)',
        r'["\']goome(?:\[[^\]]*\])?\s*(?:===|==|~=|>=|<=)\s*(?P<v>\d[^\s,;#"\']*)',
    ], "pip install -r requirements.txt", latest_pypi),
    Kind("java", names_in("gradle.properties", "build.gradle", "build.gradle.kts"), [
        r'^[ \t]*goome_version[ \t]*=[ \t]*(?P<v>[^\s#]+)',
        r'io\.github\.goome-ui:goome:(?P<v>\d[^"\'\s)]*)',
    ], "./gradlew build --refresh-dependencies", latest_maven),
    Kind("rust", names_in("Cargo.toml"), [
        r'^[ \t]*goome[ \t]*=[ \t]*"[\^=~]?(?P<v>[^"]+)"',
        r'^[ \t]*goome[ \t]*=[ \t]*\{[^}\n]*?\bversion[ \t]*=[ \t]*"[\^=~]?(?P<v>[^"]+)"',
        r'^\[(?:[\w.-]+\.)?dependencies\.goome\][^\[]*?^version[ \t]*=[ \t]*"[\^=~]?(?P<v>[^"]+)"',
    ], "cargo update -p goome", latest_crate),
    NodeKind("node", names_in("package.json"), [
        r'node-goome/releases/download/v(?P<v>[^/"]+)/goome-',
    ], "npm install", latest_release("node-goome")),
    Kind("go", names_in("go.mod"), [
        r'github\.com/goome-ui/go-goome[ \t]+v(?P<v>[^\s/]+)',
    ], "go mod tidy", latest_go),
    ZigKind("zig", names_in("build.zig.zon"), [
        r'zig-goome/archive/refs/tags/v(?P<v>[^"/]+?)\.tar\.gz',
    ], "zig build", latest_release("zig-goome")),
    LuaKind("lua", lambda n: n.endswith(".rockspec"), [], "luarocks make", latest_release("lua-goome")),
    Kind("godot", names_in("get-goome.sh", "get-goome.ps1"), [
        r'GOOME_VERSION:-(?P<v>[^}\s]+)\}',
        r'else \{ "(?P<v>[^"]+)" \}',
    ], "run get-goome.sh", latest_release("godot-goome")),
    CKind("c", names_in("goome.h"), [
        r'^#define GOOME_VERSION "(?P<v>[^"]+)"',
    ], None, latest_release("c-goome")),
]


def find_project(start):
    if not os.path.isdir(start):
        raise UpgradeError(2, "%s isnt a folder" % start)
    folder = start
    while True:
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            entries = []
        for kind in KINDS:
            for name in entries:
                path = os.path.join(folder, name)
                if kind.wanted(name) and os.path.isfile(path) and kind.read(path):
                    return kind, folder
        up = os.path.dirname(folder)
        if up == folder:
            raise UpgradeError(2, "not a goome project, found no goome pin in %s or the folders above it" % start)
        folder = up


def collect_pins(kind, root):
    pins = []
    for top, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SCAN_SKIP and not d.startswith("."))
        for name in sorted(files):
            if kind.wanted(name):
                pin = kind.read(os.path.join(top, name))
                if pin:
                    pins.append(pin)
    return pins


def inside(root, path):
    base = os.path.realpath(root)
    return os.path.realpath(path).startswith(base + os.sep)


def write_change(root, path, new_path, text):
    target = new_path or path
    if not inside(root, path) or not inside(root, target):
        raise UpgradeError(3, "%s is outside the project, not touching it" % target)
    folder = os.path.dirname(target)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".goome-upgrade-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if new_path and os.path.abspath(new_path) != os.path.abspath(path) and os.path.exists(path):
        os.remove(path)


def run_upgrade(a):
    start = os.path.abspath(a.dir or ".")
    kind, root = find_project(start)
    pins = collect_pins(kind, root)
    latest = kind.latest()
    stables = [p for p in pins if is_stable(p.version)]
    behind = [p for p in stables if is_newer(latest, p.version)]
    current = min(stables, key=lambda p: parse_version(p.version)).version if stables else pins[0].version
    info = {"ok": True, "lang": kind.name, "root": root, "current": current, "latest": latest, "update": bool(behind), "files": [], "next": kind.next}
    if not behind:
        if not stables:
            info["note"] = "the pin %s isnt a stable version, left alone" % current
        return info, 0
    plan = []
    for pin in behind:
        plan.extend(kind.changes(root, pin, latest, True))
    for path, new_path, _ in plan:
        for p in (path, new_path):
            rel = os.path.relpath(p, root).replace(os.sep, "/") if p else None
            if rel and rel not in info["files"]:
                info["files"].append(rel)
    if a.check:
        return info, 10
    work = []
    for pin in behind:
        work.extend(kind.changes(root, pin, latest, False))
    for path, new_path, text in work:
        write_change(root, path, new_path, text)
    info["applied"] = True
    info["version"] = latest
    return info, 0


def cmd_upgrade(a):
    try:
        info, code = run_upgrade(a)
    except UpgradeError as e:
        if a.json:
            print(json.dumps({"ok": False, "error": e.message}))
        else:
            print("goome: " + e.message, file=sys.stderr)
        return e.code
    if a.json:
        print(json.dumps(info))
        return code
    names = ", ".join(info["files"])
    if info.get("note"):
        print("goome: %s project, %s" % (info["lang"], info["note"]))
    elif not info["update"]:
        print("goome: %s project, goome %s is the newest" % (info["lang"], info["current"]))
    elif a.check:
        print("goome: %s project, goome %s -> %s is out (%s), run goome upgrade" % (info["lang"], info["current"], info["latest"], names))
    else:
        print("goome: %s project, goome %s -> %s in %s" % (info["lang"], info["current"], info["latest"], names))
        if info["next"]:
            print("next: " + info["next"])
    return code


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
    p = argparse.ArgumentParser(prog="goome", description="makes a new goome project from a template, builds apps for the web, moves a project to the newest goome")
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
    u = sub.add_parser("update", help="update goome-cli itself to the newest version")
    u.add_argument("--check", action="store_true", help="only print the newest version")
    g = sub.add_parser("upgrade", help="update the goome version your project uses")
    g.add_argument("--check", action="store_true", help="only look, change nothing, exit 10 if theres a newer goome")
    g.add_argument("--json", action="store_true", help="print the result as one json object")
    g.add_argument("--dir", help="a folder in the project, the current one by default")
    a = p.parse_args(argv)
    cmds = {"new": cmd_new, "build": cmd_build, "serve": cmd_serve, "list": cmd_list, "update": cmd_update, "upgrade": cmd_upgrade}
    if a.cmd not in cmds:
        p.print_help()
        return 1
    code = cmds[a.cmd](a)
    if a.cmd in ("new", "build", "list"):
        update_note()
    return code


if __name__ == "__main__":
    sys.exit(main())
