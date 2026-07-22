# Deploy

Stack: DigitalOcean Droplet (Docker) + Cloudflare (DNS and HTTPS).

Visitors hit Cloudflare over HTTPS. Cloudflare forwards HTTP to the Droplet on port 80, which runs the app container. Votes are stored in a Docker volume.

## Cloudflare

1. Create an A record pointing at the Droplet's IPv4 address.
2. Enable the proxy (orange cloud).
3. Under SSL/TLS, set the encryption mode to **Flexible**.

Repeat for `www` if you use that hostname.

## Droplet setup

Install Docker:

```bash
sudo apt update
sudo apt install -y git curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Log out and back in, then allow inbound TCP **22** and **80** on the firewall.

## Install the app

```bash
sudo mkdir -p /opt/banlist
sudo chown "$USER":"$USER" /opt/banlist
git clone https://github.com/YOUR_USER/YOUR_REPO.git /opt/banlist
cd /opt/banlist
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `.env` as `SECRET_KEY=...` (that file should only contain the secret key).

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web flask sync-cards
```

Site: https://unbanthisyoucowards.net

Re-run `flask sync-cards` when NSG updates the Standard banlist or card pool.

## Updating

```bash
cd /opt/banlist
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Do not pass `-v` to `docker compose down` unless you intend to delete the vote database.

## Commands

```bash
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml exec web flask sync-cards
docker compose -f docker-compose.prod.yml down
```
