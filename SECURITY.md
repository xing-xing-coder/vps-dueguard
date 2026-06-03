# Security Policy

## Reporting Security Issues

Please do not open public GitHub issues for vulnerabilities, leaked credentials, tokens, cookies, provider account data, or sensitive VPS information.

Report security concerns privately by contacting the repository owner through GitHub. Include a clear description, affected version or commit, reproduction steps if safe to share, and any relevant logs with secrets removed.

## Sensitive Data

VPS DueGuard stores provider credentials, Telegram bot tokens, cookies, and notification state locally on the user's own machine or VPS. Do not publish:

- `config.yaml`
- `.vps_sessions/`
- `.vps_dueguard_state.json`
- screenshots that include tokens, account details, service identifiers, renewal dates, traffic data, or provider URLs
- logs that include credentials, cookies, tokens, or account-specific data

## Responsible Use

VPS DueGuard is intended only for accounts and provider panels that you own or are explicitly authorized to manage. It must not be used to bypass CAPTCHA, 2FA, access controls, rate limits, anti-bot mechanisms, or provider restrictions.
