<p align="center">
  <img src="https://raw.githubusercontent.com/goome-ui/.github/main/profile/logo.png" alt="goome" width="150">
</p>

<h1 align="center">🪄 goome-cli 🪄</h1>

<p align="center">
<b><code>goome new</code> makes you a new goome project, already named and ready to build. C, C#, Python, Java, Godot, Rust, Node, Go, Zig or Lua.</b>
</p>

<p align="center">
  <img src="https://goome.wtf/badges/python-38.svg" alt="Python 3.8+">
  <img src="https://goome.wtf/badges/one-file-goome-py.svg" alt="one file">
  <img src="https://img.shields.io/badge/license-GPL--3.0-1b1d22?style=flat-square" alt="GPL-3.0">
</p>

<p align="center">
  It grabs one of the goome app templates from GitHub, puts your name in everywhere and tells you how to run it. Its one Python file with nothing to install besides Python itself.<br> <br>
  Do you like this project? If so, please let me know!
  <a href="https://sevvy-wevvy.com/discord">Discord</a>
</p>

<p align="center">
  <a href="https://goome.wtf/docs/">Docs</a> &nbsp;·&nbsp;
  <a href="https://github.com/goome-ui/c-goome">goome</a> &nbsp;·&nbsp;
  <a href="https://github.com/goome-ui/examples">Examples</a>
</p>

<p align="center">
  To see goome before you start, the <a href="https://goome.wtf/docs/downloads/">ready made apps</a> are on the <a href="https://github.com/goome-ui/examples/releases/latest">examples release</a>.<br>
  Questions go in <a href="https://github.com/goome-ui/c-goome/discussions">Discussions</a>, and the <a href="https://github.com/goome-ui/c-goome/labels/good%20first%20issue">good first issues</a> on c-goome are small ones if you want to help.
</p>

```sh
goome new my-overlay --lang python
cd my-overlay
pip install -r requirements.txt
python main.py
```

<details>
<summary align="center"><b>⬇️ Get It ⬇️</b></summary>

<br>

```sh
pipx install goome-cli
goome --version
```

<p align="center">
Its on <a href="https://pypi.org/project/goome-cli/">PyPI</a> as <code>goome-cli</code>, and the command it gives you is <code>goome</code>. <code>pipx</code> keeps it away from your other Python stuff, <code>pip install goome-cli</code> works too.<br>
Not the same as <code>pip install goome</code>, that one is <a href="https://github.com/goome-ui/python-goome">python-goome</a>, the library.<br> <br>
Or skip installing and just download the file, it runs the same way:
</p>

```sh
curl -fsSL -o goome.py https://raw.githubusercontent.com/goome-ui/goome-cli/main/goome.py
python goome.py new my-app --lang c
```

<p align="center">
On windows thats <code>irm https://raw.githubusercontent.com/goome-ui/goome-cli/main/goome.py -OutFile goome.py</code> in powershell, then <code>python goome.py new ...</code>.<br> <br>
For a certain version use <code>pip install goome-cli==0.5.4</code>, or put the tag after an <code>@</code> to get it from git, like <code>pip install git+https://github.com/goome-ui/goome-cli@v0.5.4</code>.
</p>
</details>

<details>
<summary align="center"><b>🚀 How To Use 🚀</b></summary>

<br>

```sh
goome new <name> --lang c|csharp|python|java|godot|rust|node|go|zig|lua [--template app|overlay|mod-menu|hud]
goome list
goome update [--check]
goome --version
```

<p align="center">
<b>--lang</b> - which language, theres a template repo for each one<br>
<b>--template</b> - which starting point, <code>app</code> if you leave it out<br>
<b>--dir</b> - the folder to make it in, the name if you leave it out<br>
<b>--ref</b> - a branch, tag or commit of the template repo<br>
<b>--from</b> - a template folder or .tar.gz you already have, nothing gets downloaded<br> <br>
The templates:<br> <br>
<b>app</b> - a normal window, and a toggle that turns it into an overlay<br>
<b>overlay</b> - a see-through overlay, only the window takes clicks<br>
<b>mod-menu</b> - a menu over the game, a hotkey opens and closes it<br>
<b>hud</b> - a little info panel in the corner, clicks go straight through it<br> <br>
It downloads the template that matches this version of goome-cli, and the newest one on main if theres no tag for it yet.<br>
The name can be anything with letters and numbers. <code>cool hud</code> turns into "Cool Hud" in titles, <code>cool-hud</code> for the binary, <code>CoolHud</code> for the C# project and <code>coolhud</code> for the Java package.<br>
It wont touch a folder that already has stuff in it.<br> <br>
<b>goome update</b> updates goome-cli. If you installed it with pip or pipx it runs the right upgrade for that, if its the loose <code>goome.py</code> it downloads the newest one from the releases and swaps itself, keeping the old one as <code>goome.py.bak</code>. <code>--check</code> only prints the newest version. About once a day it says on stderr when a new version is out, <code>GOOME_NO_UPDATE_CHECK=1</code> turns that off.
</p>
</details>

<details>
<summary align="center"><b>🌐 Run It In The Browser 🌐</b></summary>

<br>

```sh
goome build --web [file.c] [--out web] [--goome DIR] [--ref REF] [--more a.c b.c]
goome serve [web] [--port 8000] [--bind 127.0.0.1]
```

<p align="center">
Compiles a goome C app to webassembly and puts a page around it. You get <code>index.html</code>, <code>goome.js</code> and <code>goome.wasm</code> in the out folder, drop it on any static host.<br> <br>
<b>file.c</b> - your app, <code>main.c</code> or <code>src/main.c</code> if you leave it out<br>
<b>--out</b> - where it goes, <code>web</code> if you leave it out<br>
<b>--goome</b> - a c-goome checkout to build with, otherwise it looks next to your app and then downloads one<br>
<b>--ref</b> - a branch or tag of c-goome to download<br>
<b>--more</b> - more .c files that belong to the app<br> <br>
You need <code>clang</code> with the wasm32 target and <code>wasm-ld</code> (<code>sudo apt install clang lld</code>, <code>brew install llvm lld</code>, <code>winget install LLVM.LLVM</code>) and bash. It says so if they are missing, <code>CLANG</code> and <code>WASM_LD</code> point it at ones in odd places.<br> <br>
Only apps work, a normal window, since the page is the window. Overlays and mod menus get an error that says why, and the app has no title bar of its own in the page. The loop in <code>main</code> has to be split in <code>goome_web_init</code> and <code>goome_web_frame</code>, a browser cant wait inside a loop. The details and the two examples are in <a href="https://github.com/goome-ui/c-goome/tree/dev/wasm/web">wasm/web</a>.
</p>
</details>

<details>
<summary align="center"><b>🧩 The Templates 🧩</b></summary>

<br>

<p align="center">
Each one is a normal GitHub template repo too, so <b>Use this template</b> works without the cli:<br> <br>
<a href="https://github.com/goome-ui/goome-app-template-c">goome-app-template-c</a><br>
<a href="https://github.com/goome-ui/goome-app-template-csharp">goome-app-template-csharp</a><br>
<a href="https://github.com/goome-ui/goome-app-template-python">goome-app-template-python</a><br>
<a href="https://github.com/goome-ui/goome-app-template-java">goome-app-template-java</a><br>
<a href="https://github.com/goome-ui/goome-app-template-godot">goome-app-template-godot</a><br>
<a href="https://github.com/goome-ui/goome-app-template-rust">goome-app-template-rust</a><br>
<a href="https://github.com/goome-ui/goome-app-template-node">goome-app-template-node</a><br>
<a href="https://github.com/goome-ui/goome-app-template-go">goome-app-template-go</a><br>
<a href="https://github.com/goome-ui/goome-app-template-zig">goome-app-template-zig</a><br>
<a href="https://github.com/goome-ui/goome-app-template-lua">goome-app-template-lua</a><br> <br>
The other starting points live in <code>variants/</code> in each one, the cli copies the one you picked over the app.
</p>
</details>

<details>
<summary align="center"><b>🛠 Pull Requests 🛠</b></summary>

<br>

<p align="center">
Want to help with goome-cli? Make A pull request to <b>dev</b>!<br>
It has to stay one file and only use what comes with Python. Template fixes go to the template repos.<br> <br>
As long as it works, and doesnt vary off too far from the main idea its very likely it get accepted!<br>
Read <a href="CONTRIBUTING.md">CONTRIBUTING.md</a> before you send one.
</p>
</details>

<details>
<summary align="center"><b>⚖️ License ⚖️</b></summary>

<br>

<p align="center">
goome-cli is under the <a href="LICENSE">GPL-3.0</a>.<br> <br>
<sub>
• You can use it, change it and share it<br>
• If you share something made with it, you have to share your source too, under the same license<br>
• Keep the credits
</sub><br> <br>
In short: play fair, keep it open, and give credit where it's due.
</p>
</details>

<details>
<summary align="center"><b>🩷 Donate 🩷</b></summary>

<br>

<p align="center">
<a href="https://sevvy-wevvy.com/kofi">Ko-fi</a> (Preferred)<br>
<a href="https://sevvy-wevvy.com/patreon">Patreon</a><br>
<a href="https://sevvy-wevvy.com/throne">Throne</a>
</p>
</details>

<p align="center">
<b>🫶 Contributors 🫶</b><br>
Thanks to everyone who helped out!<br> <br>
<a href="https://github.com/goome-ui/goome-cli/graphs/contributors"><img src="https://contrib.rocks/image?repo=goome-ui/goome-cli" alt="contributors"></a>
</p>
