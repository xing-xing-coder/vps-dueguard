# VPS DueGuard

[English](README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Debian%20%7C%20Ubuntu-30A3DC?style=for-the-badge&logo=linux&logoColor=white)](#quick-start)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20Ready-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](#telegram-bot)
[![WHMCS](https://img.shields.io/static/v1?label=Panel&message=WHMCS%20%7C%20Lagom-like&color=0F766E&style=for-the-badge)](#compatibility-notes)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

VPS DueGuard is a small tool for monitoring multiple WHMCS/Lagom-like VPS provider panels. It helps you view active services, renewal dates, and traffic usage, and sends renewal reminders, daily reports, and bot query results through Telegram.

This project is built for small VPS users who buy services from multiple providers. It is lighter than a full monitoring stack and more convenient than logging into every provider panel by hand.

## Why VPS DueGuard

Many low-cost VPS providers use similar WHMCS/Lagom client area templates. The data you need is usually there, but it is scattered across different accounts and panels.

VPS DueGuard focuses on this specific workflow:

- add providers once
- reuse login sessions where possible
- query active VPS services from all providers
- see renewal and traffic information in one output
- receive Telegram reminders before renewals
- ask a Telegram Bot for the latest summary anytime

## Legal and Responsible Use

VPS DueGuard is intended only for monitoring VPS accounts that you own or are explicitly authorized to manage. You are responsible for ensuring that your use of this tool complies with the terms of service of each provider you configure.

This project does not bypass CAPTCHA, 2FA, access controls, rate limits, or anti-bot mechanisms, and it must not be used to access accounts, systems, or provider panels without authorization.

WHMCS, Lagom, Telegram, Python, and provider names mentioned in this project are trademarks or names of their respective owners. This project is independent and is not affiliated with, endorsed by, sponsored by, or officially supported by those parties.

The software is provided as-is under the MIT License. The author is not responsible for account restrictions, provider policy violations, data loss, service interruption, or other consequences caused by improper use.

## Features

| Feature | Description |
| --- | --- |
| Unified VPS inventory | List active VPS services across multiple WHMCS/Lagom-like providers |
| Active services only | Filter out cancelled, terminated, and other inactive services |
| Traffic overview | Show used/total traffic and remaining traffic when exposed by the provider panel |
| Renewal reminders | Send Telegram reminders before configured renewal windows |
| Daily reports | Send a daily Telegram summary of active VPS services |
| Telegram Bot queries | Query summaries, traffic, renewals, or one provider from Telegram |
| Cookie session cache | Reuse provider login cookies to reduce repeated logins and speed up queries |
| Menu-first Linux deployment | Install, configure, test, manage services, view logs, and uninstall from one menu |
| Clean uninstall | Remove project-owned app files, runtime, systemd units, cookies, state, and shortcut |

## Compatibility Notes

VPS DueGuard is designed for WHMCS/Lagom-like client area panels, but compatibility depends on each provider's page layout, login flow, account security settings, and terms of service.

Compatibility notes in this project are informational only. They do not imply affiliation, authorization, endorsement, sponsorship, or official support from any provider or platform.

In many cases, a provider using a similar client area can be tried by adding its URL and account credentials in `config.yaml`. Always confirm that automated login, page parsing, cookie reuse, and notification integration are allowed for your account and provider.

## Supported Panel Scope

VPS DueGuard currently targets WHMCS/Lagom-like client areas.

Supported behavior:

- username/password login
- English client area pages where available
- service list parsing
- service detail page parsing
- renewal date extraction
- traffic usage and remaining traffic extraction when visible
- detection of common blockers such as captcha, 2FA, and failed login pages

This project detects common blockers but does not bypass them. Do not use it to circumvent CAPTCHA, 2FA, access controls, rate limits, anti-bot checks, or provider restrictions.

If a panel does not expose traffic information, the service is still included and the traffic field is shown as `unknown`.

## Quick Start

On Debian or Ubuntu:

```bash
git clone https://github.com/xing-xing-coder/vps-dueguard.git
cd vps-dueguard
sudo bash vpsm.sh
```

The script opens a bilingual menu. Choose a language, install the app, add providers, test queries, configure Telegram, and enable services.

After installation, open the menu anytime:

```bash
vpsm
```

For normal Linux deployment, `vpsm` is the main entry point. You do not need to remember Python commands.

## Menu Overview

```text
VPS DueGuard Setup

1. Install / Update VPS DueGuard
2. Provider management
3. Telegram and notification management
4. Query and test
5. systemd service management
6. Show logs
7. Uninstall completely
8. Exit
```

The menu supports:

- install or update VPS DueGuard
- add, view, or rewrite provider configuration
- test all providers or one selected provider
- configure Telegram Bot token and chat ID
- configure renewal reminder days
- send Telegram test messages
- send one daily report
- run one renewal reminder check
- start, stop, restart, and inspect the Telegram Bot service
- enable or disable daily and renewal timers
- view recent systemd logs
- uninstall all project-owned files

## Provider Configuration

The Linux menu writes:

```text
/opt/vps-dueguard/config.yaml
```

Example:

```yaml
providers:
  - name: provider-a
    base_url: https://example-provider-a.com/
    username: your@email.com
    password: your-password

  - name: provider-b
    base_url: https://example-provider-b.com/
    username: your@email.com
    password: your-password
```

Provider names are normalized to lowercase. You can later query one provider from the menu or with the Telegram command `/provider provider-a`.

## Telegram Bot

Add the Bot Token and Chat ID from the menu:

```yaml
telegram:
  bot_token: "123456:your-bot-token"
  chat_id: "123456789"
```

Only the configured `chat_id` can query VPS information.

Available commands:

| Command | Description |
| --- | --- |
| `/summary` | Show all active VPS services, renewal dates, and traffic |
| `/traffic` | Show traffic usage and remaining traffic |
| `/renewals` | Show renewal dates and days left |
| `/provider provider-a` | Query a single configured provider |
| `/refresh` | Force a fresh query and refresh the 5-minute cache |
| `/help` | Show command help |

The bot reloads `config.yaml` when the file changes. If you update providers from the menu while the bot is running, send `/refresh` and the bot will use the latest configuration.

## Renewal Reminders

Default reminder days:

```text
21,14,7,3
```

The menu accepts comma-separated numbers only, for example:

```text
21,14,7,3
```

Reminder windows are inclusive. If you configure `30` days and a VPS has `21` days left, the `30`-day reminder window can trigger once.

Duplicate reminders are prevented by the local state file:

```text
/opt/vps-dueguard/.vps_dueguard_state.json
```

The deduplication key includes provider, service name, renewal date, and reminder threshold.

## Cookie Sessions

Cookie sessions are enabled by default:

```yaml
sessions:
  enabled: true
  session_dir: ".vps_sessions"
```

Each provider has its own cookie file. The tool tries cached cookies first. If a session is invalid, it logs in again and updates the cookie.

This reduces repeated login attempts and makes Telegram queries faster after the first run.

## Linux Installation Details

The installer uses project-owned paths:

| Item | Path |
| --- | --- |
| Application | `/opt/vps-dueguard` |
| Python virtual environment | `/opt/vps-dueguard/.venv` |
| Standalone Python runtime | `/opt/vps-dueguard-runtime` |
| Shortcut command | `/usr/local/bin/vpsm` |
| Config file | `/opt/vps-dueguard/config.yaml` |
| Cookie sessions | `/opt/vps-dueguard/.vps_sessions` |
| Notification state | `/opt/vps-dueguard/.vps_dueguard_state.json` |

If the server only has an old Python version such as Python 3.7, the installer uses `uv` to install a standalone Python 3.11 runtime under `/opt/vps-dueguard-runtime`. The warning that `/root/.local/bin` is not on `PATH` can be ignored because the script uses absolute paths for the standalone Python runtime.

## systemd Services And Timers

The installer creates:

| Unit | Purpose |
| --- | --- |
| `vps-dueguard-bot.service` | Runs the Telegram long-polling bot |
| `vps-dueguard-daily.timer` | Runs the daily Telegram report |
| `vps-dueguard-renewals.timer` | Runs renewal reminder checks |

You can manage these from the menu or manually:

```bash
sudo systemctl restart vps-dueguard-bot.service
sudo systemctl status vps-dueguard-bot.service
sudo systemctl list-timers 'vps-dueguard-*'
```

View logs:

```bash
sudo journalctl -u vps-dueguard-bot.service -n 100 --no-pager
sudo journalctl -u vps-dueguard-daily.service -n 100 --no-pager
sudo journalctl -u vps-dueguard-renewals.service -n 100 --no-pager
```

## Uninstall

Open the menu:

```bash
vpsm
```

Choose **Uninstall completely**.

The uninstall flow uses two empty Enter confirmations. Entering any non-empty text cancels the uninstall.

It removes:

- `/opt/vps-dueguard`
- `/opt/vps-dueguard-runtime`
- `/usr/local/bin/vpsm`
- all `vps-dueguard-*` systemd units
- config file
- provider cookies
- notification state
- the original cloned source directory, only when project safety markers are detected

It does not remove shared system packages such as `curl`, `wget`, `rsync`, or system Python. It also does not remove user-level uv cache/config files such as `/root/.config/uv` or `/root/.cache/uv`, because those may be used by other projects.

## Local Development

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
```

Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
```

Direct Python commands are available for development and debugging:

```bash
python -m vps_dueguard list
python -m vps_dueguard list --provider provider-a
python -m vps_dueguard list --json
python -m vps_dueguard notify test
python -m vps_dueguard notify daily
python -m vps_dueguard notify renewals
python -m vps_dueguard bot
```

## Troubleshooting

### Telegram returns `No providers configured`

Open the menu:

```bash
vpsm
```

Go to provider management, add at least one provider, test the query, then send `/refresh` in Telegram.

### Telegram returns no active services

Possible causes:

- the provider account has no active VPS
- the provider panel changed its HTML layout
- login failed
- captcha or 2FA blocked login
- cookies expired and re-login failed
- provider URL, username, or password is incorrect

Run provider tests from the menu and check logs:

```bash
sudo journalctl -u vps-dueguard-bot.service -n 100 --no-pager
```

### Query is slow

The first query may be slow because it logs into each provider and reads service detail pages. Later queries should be faster because cookies and the 5-minute bot cache are used.

Use `/refresh` only when you need fresh data.

## Privacy And Safety

- `config.yaml` contains plaintext provider passwords and Telegram token.
- `config.yaml`, cookie sessions, state files, caches, and virtual environments are ignored by git.
- The Linux menu writes `config.yaml` with `600` permissions.
- Do not share config files, cookies, screenshots, logs, or Telegram bot output in public issues if they contain account, token, service, renewal, traffic, or URL details.
- The Telegram Bot only responds to the configured `chat_id`.
- The uninstall script checks project markers and high-risk paths before deleting the cloned source directory.
- Security issues should be reported privately; see [SECURITY.md](SECURITY.md).

## Project Layout

```text
vps_dueguard/
  client.py          # login, session cache, provider fetching
  parser.py          # WHMCS/Lagom page parsing
  notifications.py   # Telegram, reports, reminders, bot commands
  menu_config.py     # safe YAML read/write helpers for vpsm.sh
  cli.py             # Typer CLI
tests/               # parser, config, session, notification tests
vpsm.sh              # Linux menu installer and manager
config.example.yaml  # example config
```

## License

This project is licensed under the [MIT License](LICENSE).

Direct third-party dependencies and license notes are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
