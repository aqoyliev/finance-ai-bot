# Deploy on Oracle Cloud Always Free (arm64, no domain)

Runs the bot and its Mini App on one Oracle VM with Docker Compose:

- `bot` — built from the repo `Dockerfile`; SQLite lives in `deploy/oracle/data/finance.db`.
  Its web port is **not** published; only Caddy can reach it.
- `caddy` — public on 80/443, gets a Let's Encrypt certificate automatically and proxies to the bot.

No domain is needed: [sslip.io](https://sslip.io) turns the VM's IP into a hostname,
e.g. `152.70.1.2` → `152-70-1-2.sslip.io`.

> **Only one copy of the bot may run at a time.** Telegram allows a single `getUpdates`
> poller per token. Stop the Railway service **before** starting this one, or both will
> log `TerminatedByOtherGetUpdates` / "Conflict" errors.

## 1. Create the VM (Oracle console)

1. **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 22.04 or 24.04**
   - Shape: **VM.Standard.A1.Flex** (Ampere, arm64), e.g. **2 OCPU / 12 GB** (Always Free covers up to 4 OCPU / 24 GB in total)
   - Networking: public subnet, **assign a public IPv4 address**
   - Add your SSH public key
2. **Networking → Virtual cloud networks → your VCN → Security Lists → Default security list → Add Ingress Rules**
   - Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port **80**
   - Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port **443**

   (Port 22 is already open. The host's own iptables rules are opened by `setup.sh`.)

If you get "Out of capacity" for A1, retry later or in another availability domain.

## 2. Bootstrap the server

```bash
ssh ubuntu@<PUBLIC_IP>
git clone https://github.com/aqoyliev/finance-ai-bot.git
cd finance-ai-bot
bash deploy/oracle/setup.sh
exit            # log out and back in so the docker group applies
```

`setup.sh` installs Docker + the compose plugin, opens TCP 80/443 in iptables (persisted),
adds a 2 GB swapfile and enables unattended security upgrades. It is safe to re-run.

## 3. Configure

```bash
ssh ubuntu@<PUBLIC_IP>
cd ~/finance-ai-bot/deploy/oracle
cp .env.example .env
nano .env
```

Set at least:

| Variable | Example |
|---|---|
| `PUBLIC_HOST` | `152-70-1-2.sslip.io` |
| `WEBAPP_URL` | `https://152-70-1-2.sslip.io` (must be `https://` + `PUBLIC_HOST`) |
| `BOT_TOKEN`, `ADMINS` | as on Railway |
| `GEMINI_API_KEY` (or `AI_PROVIDER=claude` + `ANTHROPIC_API_KEY`) | as on Railway |

`DATABASE_URL`, `PORT` and `WEBAPP_HOST` are fixed in `docker-compose.yml`. Leave the optional
model/timeout lines commented out unless you want to override them (empty values break startup).

## 4. (Optional) Bring the database over from Railway

Do this **before the first start**, so the bot does not create an empty database first.

1. Download `/data/finance.db` from the Railway volume (e.g. `railway ssh` / a volume backup).
2. Stop the Railway service.
3. Upload it from your computer:

   ```bash
   scp finance.db ubuntu@<PUBLIC_IP>:~/finance-ai-bot/deploy/oracle/data/finance.db
   ```

## 5. Start

```bash
cd ~/finance-ai-bot/deploy/oracle
docker compose up -d --build      # first build on arm64 takes a few minutes
docker compose ps
```

Open `https://<PUBLIC_HOST>` in a browser — you should get a valid certificate.
Then send `/start` to the bot.

## Logs

```bash
docker compose logs -f bot        # bot
docker compose logs -f caddy      # certificates / proxy
```

Logs are rotated (3 × 10 MB per container).

## Update to the latest code

```bash
cd ~/finance-ai-bot
git pull
cd deploy/oracle
docker compose up -d --build
docker image prune -f             # optional: drop old image layers
```

## Backup and restore

The whole state is one file: `deploy/oracle/data/finance.db`.

**Daily backup on the VM.** `backup.sh` takes an online copy with SQLite's backup API (no downtime),
checks `pragma integrity_check`, gzips it to `backups/finance-YYYYMMDD-HHMM.db.gz` and keeps 14 days
(`KEEP_DAYS`). Install it in root's crontab (21:15 UTC = 02:15 Tashkent):

```bash
cd ~/finance-ai-bot/deploy/oracle && chmod +x backup.sh && sudo ./backup.sh   # one run to test
line="15 21 * * * $PWD/backup.sh >> /var/log/finance-bot-backup.log 2>&1"
{ sudo crontab -l 2>/dev/null | grep -v backup.sh || true; echo "$line"; } | sudo crontab -
```

**Copy to a Windows PC.** `pull-backups.ps1` copies `backups/*.gz` into `deploy/oracle/backups/` on the PC
(gitignored) and logs to `pull.log` there. Schedule it daily; `-AllowStartIfOnBatteries` matters on a laptop,
otherwise the task stays "Queued" on battery:

```powershell
$script = "D:\projects\test\deploy\oracle\pull-backups.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "FinanceBot DB backup pull" -Action $action -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00) -Settings $settings
```

Restore:

```bash
cd ~/finance-ai-bot/deploy/oracle
docker compose stop bot
gunzip -c backups/finance-YYYYMMDD-HHMM.db.gz > data/finance.db
docker compose start bot
```

## Notes

- **Let's Encrypt + sslip.io:** certificates for `*.sslip.io` share Let's Encrypt's
  per-domain rate limit with everyone else using sslip.io, so issuance can occasionally fail
  with `rateLimited`. Caddy retries on its own (and can fall back to ZeroSSL). The
  `caddy_data` volume keeps the certificate, so don't delete it — that avoids re-issuing.
  If it keeps failing, use any cheap/free domain pointing at the IP and change `PUBLIC_HOST`.
- If the VM's public IP changes, update `PUBLIC_HOST`, `WEBAPP_URL` and run `docker compose up -d`.
- Memory: the bot plus headless Chromium (report cards) fits easily in 12 GB; the swapfile
  is a safety net for smaller shapes.
