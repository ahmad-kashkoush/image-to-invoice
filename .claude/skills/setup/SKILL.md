---
name: setup
description: Use when setting up this repo for local development for the first time, after a fresh clone, or when re-provisioning a broken environment — creates the virtualenv, installs dependencies, and configures the .env file.
---

# Project Setup

## Overview

Bootstraps a working local environment: virtualenv, dependencies, `.env`.

The full workflow runs on **Windows** (`pywinauto`'s `uia` backend is
Windows-only), against a live Fakturama window. The same steps work on
macOS/Linux for developing `extraction` and `normalization`, which have no
`pywinauto` dependency (`CLAUDE.md`'s Platform note) — only the interpreter
paths differ, noted per step below.

## Steps

1. **Check Python version.** Must be `>=3.11` (`pyproject.toml`'s
   `requires-python`): `python --version` on Windows, `python3 --version`
   elsewhere. If the default interpreter is older, use whichever one
   satisfies this for the venv creation step below — don't silently proceed
   with an older one.
2. **Create the virtualenv**, if `.venv/` doesn't already exist:
   ```
   python -m venv .venv          # Windows
   python3 -m venv .venv         # macOS/Linux
   ```
3. **Install the package in editable mode with dev dependencies**:
   ```
   .venv\Scripts\python -m pip install -e ".[dev]"    # Windows
   .venv/bin/python -m pip install -e ".[dev]"        # macOS/Linux
   ```
   This installs `pywinauto`, `pywin32`, `pillow`, `anthropic`,
   `python-dotenv`, and `pytest` per `pyproject.toml` (`requirements.txt` is
   the same set, annotated, and is not installed from). `pywinauto` installs
   fine off Windows but its `uia` backend only imports on Windows —
   expected, not a failure.
4. **Set up `.env`**, if it doesn't already exist:
   ```
   copy .env.example .env        # Windows
   cp .env.example .env          # macOS/Linux
   ```
   Then ask the user for their `ANTHROPIC_API_KEY` and fill it in — never
   invent or reuse a key from elsewhere, and never commit `.env` (it's
   already in `.gitignore`). If the user doesn't have a key yet, leave the
   line blank and note that extraction calls will fail until it's set.
5. **Verify the environment** with an import check, not a test run — this
   project's verification is live-VM only (`CLAUDE.md`'s test conventions):
   ```
   .venv\Scripts\python -c "import fakturama_automation.normalization.normalizer, fakturama_automation.extraction.vision_extractor; print('ok')"
   ```
   (`.venv/bin/python` off Windows.) A clean import means the package is
   installed and its cross-platform half is ready to develop against. It
   does not verify anything that drives Fakturama's UI — `ui_automation`,
   `entity_resolution`, `verification`, `orchestrator` — which needs a real
   Fakturama window on Windows.

## When something fails

- **Wrong Python version / venv creation fails**: report the exact
  interpreter found and what's required; don't silently fall back to a
  different Python without telling the user.
- **`pip install` fails**: read the actual error before retrying — a
  missing system dependency (e.g. build tools for a C extension) needs a
  different fix than a network/proxy issue.
- **The import check fails**: report the actual `ImportError` rather than
  calling setup done. A missing module points at a stale `pyproject.toml`;
  a `pywinauto`/`uia` error off Windows is expected and not a setup gap.
