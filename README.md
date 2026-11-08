<h1 align="center">todone</h1>

<p align="center">
  <b>Every TODO in the repo, oldest first.</b>
</p>

<p align="center">
  <a href="https://github.com/Viltrumlik/todone/actions/workflows/ci.yml"><img src="https://github.com/Viltrumlik/todone/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT"></a>
</p>

`grep -r TODO` gives you a list. It does not tell you that the one at the top has been sitting there for three years — which is the only part that decides whether anybody should care.

```console
$ todone
  847d  src/billing/charge.py:91   TODO: handle partial refunds
        Alisher Muhammadaliyev
    3d  src/api/views.py:12        FIXME: this retries forever

2 markers, oldest 847 days
```

The age comes from `git blame`, so it is the age of **the line**, not of the file. Reformatting the file does not reset it; editing that line does.

## As a CI gate

```yaml
- run: pipx install git+https://github.com/Viltrumlik/todone
- run: todone --older-than 365
```

Exit `3` means something was found. So that step fails only when a marker has been ignored for a year — a rule you can actually hold, unlike "no TODOs ever".

## Options

| | |
|---|---|
| `--older-than DAYS` | only markers at least this old |
| `--tag TAG` | which markers to look for (default TODO, FIXME, HACK, XXX) |
| `--author NAME` | only lines by this author |
| `--no-author` | do not print authors |
| `--json` | machine-readable |

Exit codes: `0` nothing matched · `1` not a git repository · `2` usage · `3` markers found.

## It only reads what git tracks

An early version walked the filesystem. On a real repository that meant `node_modules`, `.build`, generated test runners and other worktrees — 38 markers, none of them the author's, and 29 seconds to find out.

`git ls-files` fixed it: `.gitignore` is respected for free, build output never appears, and every file has a blame history, so every marker has an age. The same repository now answers in one second.

## Install

```bash
pipx install git+https://github.com/Viltrumlik/todone
```

Or take the file:

```bash
curl -O https://raw.githubusercontent.com/Viltrumlik/todone/main/todone.py
python3 todone.py
```

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests build a real git repository and backdate the commits, so the age calculation is checked against real blame output rather than mocked. CI runs on Ubuntu, macOS and Windows with Python 3.9 through 3.13.

## License

[MIT](LICENSE) © Alisher Muhammadaliyev ([@Viltrumlik](https://github.com/Viltrumlik))
