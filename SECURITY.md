# Security Policy

## Supported versions

Only the latest commit on the `main` branch receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report privately using [GitHub private vulnerability reporting](https://github.com/SanTiwari07/PotHoleDetection/security/advisories/new), or email sanskartiwari.smt@gmail.com with:

- A description of the issue and its impact
- Steps to reproduce (affected file, firmware version, or configuration)
- Any suggested fix

You can expect an acknowledgement within 7 days and a status update within 30 days.

## Scope notes

- Never commit real WiFi credentials or API keys. Use `.env` (see `.env.example`) and the ESP32 credential helper `update_wifi.py`.
- If you find credentials accidentally committed, report them so they can be rotated.
