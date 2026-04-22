# Security

## Sensitive runtime files

Do not publish these files/directories from your deployment environment:

- `.env`
- `data/`
- `logs/`
- `ntqq/`
- `napcat/cache/`
- `napcat/config/onebot11_*.json`
- QR code images, cookies, login state, or adapter runtime cache

## Reporting issues

If you discover a security issue in the framework itself, please avoid posting secrets or production credentials in public issues.

## Deployment reminder

This repository is intended to be open source, but your live QQ account state and local deployment secrets must stay private.
