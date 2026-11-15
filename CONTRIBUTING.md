<h1 align="center">🛠 Contributing to goome-cli 🛠</h1>

<p align="center">
Small PRs that fix one thing are the easiest for me to check.<br>
Bugs in a template go to that template repo, bugs in goome itself to <a href="https://github.com/goome-ui/c-goome">c-goome</a>.
</p>

<details>
<summary align="center"><b>📋 The short version 📋</b></summary>

<p align="center">
• One thing per PR<br>
• Open your PR against the <b>dev</b> branch, not main<br>
• It stays one file, <code>goome.py</code>, and only uses the Python standard library<br>
• It has to keep working on Python 3.8<br>
• Dont touch the protected files, a bot closes the PR if you do<br>
• CI has to pass<br>
• AI is fine, but say you used it and know what every line does
</p>
</details>

<details>
<summary align="center"><b>🚫 What gets closed automatically 🚫</b></summary>

<p align="center">
A bot checks every PR and closes it with a comment if it hits any of these.<br> <br>
• PRs that arent against <b>dev</b><br>
• Anything in <code>.github/</code><br>
• <code>pyproject.toml</code>, it decides what pip runs when someone installs this<br>
• <code>LICENSE</code><br> <br>
Need one changed? <a href="https://github.com/goome-ui/goome-cli/issues">Open an issue</a>.
</p>
</details>

<details>
<summary align="center"><b>🧪 Testing 🧪</b></summary>

```sh
python -m unittest discover -s tests -v
python goome.py new test-app --lang c --from ../goome-app-template-c
```

<p align="center">
The tests use a fake template so they run without internet. <code>--from</code> lets you try a template folder you have locally. CI also makes every language from the real template repos, builds it and runs it on goome's test backend.
</p>
</details>

<details>
<summary align="center"><b>💬 Discussions and first issues 💬</b></summary>
<p align="center">
Questions and stuff you made with goome go in <a href="https://github.com/goome-ui/c-goome/discussions">Discussions</a>.<br>
If you want something to work on, the <a href="https://github.com/goome-ui/goome-cli/labels/good%20first%20issue">good first issue</a> ones are small. Comment on one before you start.
</p>
</details>

<details>
<summary align="center"><b>🛡️ Security 🛡️</b></summary>

<p align="center">
Found a security hole? Dont open a public issue or PR for it, read <a href="https://github.com/goome-ui/.github/blob/main/SECURITY.md">SECURITY.md</a> and tell me privately first.
</p>
</details>

<p align="center">
By sending a PR you agree your code goes out under the same <a href="LICENSE">GPL-3.0 license</a> as the rest of goome-cli.
</p>
