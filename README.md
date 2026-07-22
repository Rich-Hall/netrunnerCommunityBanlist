# Community Banlist

A Netrunner Standard community poll: vote ban or keep on cards, and compare the resulting list to NSG's latest announced banlist.

Live site: [unbanthisyoucowards.net](https://unbanthisyoucowards.net)

## Requirements

Docker with Compose.

## Local development

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# set SECRET_KEY in .env to that value

docker compose up --build -d
docker compose exec web flask sync-cards
```

Open http://localhost:5000

The included Dev Container config uses the same Compose service if you prefer to develop inside the container.

## Production

Production runs on a VPS with Docker. Cloudflare provides DNS and HTTPS. See [DEPLOY.md](DEPLOY.md).

## Lint

```bash
ruff check .
ruff format .
```
