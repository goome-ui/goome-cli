#!/usr/bin/env python3
import argparse
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

__version__ = "0.5.0"

ORG = "goome-ui"
LANGS = {
    "c": "C, one goome.h, builds with any C compiler",
    "csharp": "C#, .NET 8 or newer",
    "python": "Python 3.8 or newer",
    "java": "Java 22 or newer, Gradle",
    "godot": "Godot 4.4 or newer, GDScript",
}
TEMPLATES = {
    "app": "a normal window, with a toggle that turns it into an overlay",
    "overlay": "a see-through overlay, only the window takes clicks",
    "mod-menu": "a menu over the game that a hotkey opens and closes",
    "hud": "a little info panel in the corner, clicks go through it",
}
TEMPLATE_ONLY = ["variants", "tests", "CONTRIBUTING.md", ".github/workflows/pr-rules.yml"]
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


def next_steps(lang, folder, kebab):
    cd = "cd " + (folder if " " not in folder else '"%s"' % folder)
    steps = {
        "c": [cd, "cc -O2 -o %s main.c goome.c" % kebab, "./" + kebab, "",
              "or with cmake (windows too):", "cmake -S . -B build", "cmake --build build"],
        "csharp": [cd, "dotnet run"],
        "python": [cd, "python -m venv .venv", "source .venv/bin/activate   (.venv\\Scripts\\activate on windows)",
                   "pip install -r requirements.txt", "python main.py"],
        "java": [cd, "./gradlew run   (gradlew.bat run on windows)"],
        "godot": [cd, "./get-goome.sh   (or get-goome.ps1 on windows)", "godot -e --path ."],
    }
    return steps[lang]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "goome-cli/" + __version__})
    with urllib.request.urlopen(req, timeout=60) as r:
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
    skip = {".git", ".venv", "build", "bin", "obj", ".gradle", ".godot", "__pycache__"}
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
             "Made with [goome](https://goome-ui.github.io/docs/), from the %s %s template." % (lang, template), "",
             "```sh"] + [s for s in next_steps(lang, ".", table["my-goome-app"])[1:] if s and not s.endswith(":")] + ["```", ""]
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
    for s in next_steps(a.lang, folder, table["my-goome-app"]):
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="goome", description="makes a new goome project from a template")
    p.add_argument("--version", action="version", version="goome " + __version__)
    sub = p.add_subparsers(dest="cmd")
    n = sub.add_parser("new", help="make a new project")
    n.add_argument("name")
    n.add_argument("--lang", required=True, choices=list(LANGS))
    n.add_argument("--template", default="app", choices=list(TEMPLATES))
    n.add_argument("--dir", help="folder to make it in, the name by default")
    n.add_argument("--ref", help="branch, tag or commit of the template repo")
    n.add_argument("--from", dest="source", help="use a local template folder or .tar.gz instead of downloading")
    sub.add_parser("list", help="show the languages and templates")
    a = p.parse_args(argv)
    if a.cmd == "new":
        return cmd_new(a)
    if a.cmd == "list":
        return cmd_list(a)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
