<p align="center">
  <img src="https://raw.githubusercontent.com/goome-ui/.github/main/profile/logo.png" alt="goome" width="150">
</p>

<h1 align="center">🪄 goome-cli 🪄</h1>

<p align="center">
<b><code>goome new</code> makes you a new goome project, already named and ready to build. C, C#, Python, Java or Godot.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-6fdc5f?style=flat-square&logo=python&logoColor=1b1d22&labelColor=6fdc5f" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/one%20file-goome.py-1b1d22?style=flat-square&labelColor=6fdc5f" alt="one file">
  <img src="https://img.shields.io/badge/license-GPL--3.0-1b1d22?style=flat-square" alt="GPL-3.0">
</p>

<p align="center">
  It grabs one of the goome app templates from GitHub, puts your name in everywhere and tells you how to run it. Its one Python file with nothing to install besides Python itself.<br> <br>
  Do you like this project? If so, please let me know!
  <a href="https://sevvy-wevvy.com/discord">Discord</a>
</p>

<p align="center">
  <a href="https://goome-ui.github.io/docs/">Docs</a> &nbsp;·&nbsp;
  <a href="https://github.com/goome-ui/c-goome">goome</a> &nbsp;·&nbsp;
  <a href="https://github.com/goome-ui/examples">Examples</a>
</p>

<p align="center">
  To see goome before you start, the <a href="https://goome-ui.github.io/docs/downloads/">ready made apps</a> are on the <a href="https://github.com/goome-ui/examples/releases/latest">examples release</a>.<br>
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
pip install git+https://github.com/goome-ui/goome-cli
goome --version
```

<p align="center">
Or skip installing and just download the file, it runs the same way:
</p>

```sh
curl -fsSL -o goome.py https://raw.githubusercontent.com/goome-ui/goome-cli/main/goome.py
python goome.py new my-app --lang c
```

<p align="center">
On windows thats <code>irm https://raw.githubusercontent.com/goome-ui/goome-cli/main/goome.py -OutFile goome.py</code> in powershell, then <code>python goome.py new ...</code>.<br> <br>
For a certain version put the tag after an <code>@</code>, like <code>pip install git+https://github.com/goome-ui/goome-cli@v0.4.0</code>.
</p>
</details>

<details>
<summary align="center"><b>🚀 How To Use 🚀</b></summary>

<br>

```sh
goome new <name> --lang c|csharp|python|java|godot [--template app|overlay|mod-menu|hud]
goome list
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
It wont touch a folder that already has stuff in it.
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
<a href="https://github.com/goome-ui/goome-app-template-godot">goome-app-template-godot</a><br> <br>
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
