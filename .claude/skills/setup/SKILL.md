---
name: setup
description: Use when setting up this repo for local development for the first time, after a fresh clone, or when re-provisioning a broken environment — creates the virtualenv, installs dependencies, and configures the .env file.
---

# Project Setup

## Overview

Bootstraps a working local environment for cross-platform development
(extraction, normalization, and any pure-Python module). This does **not**
cover the Windows 11 ARM VM used for `ui_automation` against a live
Fakturama window — see `README.md`'s Platform section for that; this skill
only prepares the macOS/Linux side described in `README.md`'s "Suggested
build order" steps 1-2.

## Steps

1. **Check Python version.** `python3 --version` must be `>=3.11`
   (`pyproject.toml`'s `requires-python`). If the system default `python3`
   is older, use whichever interpreter satisfies this (`python3.11`,
   `pyenv`, etc.) for the venv creation step below.
2. **Create the virtualenv**, if `.venv/` doesn't already exist:
   ```
   python3 -m venv .venv
   ```
3. **Install the package in editable mode with dev dependencies**:
   ```
   .venv/bin/pip install -e ".[dev]"
   ```
   This installs `pywinauto`, `anthropic`, `python-dotenv`, and `pytest`
   per `pyproject.toml`. `pywinauto` installs fine off Windows but its
   `uia` backend only imports on Windows — expected, not a failure.
4. **Set up `.env`**, if it doesn't already exist:
   ```
   cp .env.example .env
   ```
   Then ask the user for their `ANTHROPIC_API_KEY` and fill it in — never
   invent or reuse a key from elsewhere, and never commit `.env` (it's
   already in `.gitignore`). If the user doesn't have a key yet, leave the
   line blank and note that extraction calls will fail until it's set.
5. **Verify the environment** by running the tests that don't require
   Windows or `pywinauto`'s `uia` backend:
   ```
   .venv/bin/pytest tests/extraction tests/normalization
   ```
   These are the two sections designed to run and test cross-platform
   (see `CLAUDE.md`'s Platform note). A clean pass means extraction and
   normalization are ready to develop against; it does not verify
   `ui_automation`, `entity_resolution`, `verification`, `orchestrator`, or
   `error_handling`, since those transitively import `pywinauto` and can
   only be exercised on the Windows VM.

## When something fails

- **Wrong Python version / venv creation fails**: report the exact
  interpreter found and what's required; don't silently fall back to a
  different Python without telling the user.
- **`pip install` fails**: read the actual error before retrying — a
  missing system dependency (e.g. build tools for a C extension) needs a
  different fix than a network/proxy issue.
- **Tests fail**: don't treat this as "setup done, tests are someone
  else's problem" — report which tests failed and the actual assertion
  output, since a fresh clone with failing tests points at either a stale
  `pyproject.toml` or a real regression, not a setup gap.
