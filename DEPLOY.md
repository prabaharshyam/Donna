# Deploying Donna to the cloud (24×7)

Donna is one container plus **one persistent volume** (database, encryption key, documents).
It needs an always-on host: the scheduler sends reminders, the Telegram bot long-polls, and
inbox scans run in the background. Serverless platforms (Vercel, Lambda) won't work.

> **Run exactly one instance.** Two copies of Donna (e.g. your Mac and the server) with the same
> Telegram bot would fight over messages and send every reminder twice. Stop the Mac copy once the
> server is live.

## Free: Google Cloud e2-micro (Always Free tier)

### 1. Create the server (one time, ~5 minutes)
1. Go to **console.cloud.google.com** → create a project (e.g. "Donna") → enable billing (a card is needed for
   verification; staying within the free tier shouldn't incur charges).
2. **Compute Engine → VM instances → Create instance**:
   - **Region**: `us-central1`, `us-west1` or `us-east1` (only these are in the free tier)
   - **Machine type**: `e2-micro`
   - **Boot disk**: Debian 12, **Standard persistent disk**, **30 GB**
   - **Firewall**: tick **Allow HTTP traffic** and **Allow HTTPS traffic**
3. *(Recommended)* **VPC network → IP addresses** → reserve the VM's external IP as **static**, so Donna's address
   never changes.
4. Check the current free-tier terms and the pricing calculator before you rely on it. Google may bill a small
   amount for the external IPv4 address. Set a **budget alert** (Billing → Budgets) at a few dollars to be safe.

### 2. Install Donna (one command)
On the VM page, click **SSH** (opens a terminal in your browser) and run:

```bash
curl -fsSL https://raw.githubusercontent.com/prabaharshyam/Donna/main/deploy/gcp/setup.sh | sudo bash
```

It asks for an admin password and your Claude API key (typed on the server, never shown), then prints your
address, e.g. `https://34-12-56-78.sslip.io`: free HTTPS based on your server's IP, no domain needed.
Have your own domain? Point an A record at the VM's IP and run `sudo DONNA_DOMAIN=donna.example.com bash setup.sh`.

### 3. Move your data
Same as below: **Download full backup** on the Mac → stop the Mac copy → **Restore from backup** on the server → turn on 2FA.

Later: `sudo donna-update` pulls the latest code from GitHub; `sudo docker logs -f donna` shows logs;
daily snapshots of Donna's data are kept in `/var/backups/donna` (last 7).

## Easiest paid option: Railway (≈ US$5/month)

1. **New project → Deploy from GitHub repo** → pick `prabaharshyam/Donna`. Railway detects the `Dockerfile`.
2. **Add a volume** to the service, mounted at **`/data`**.
3. **Variables** (service → Variables):

   | Variable | Value |
   |---|---|
   | `DONNA_ADMIN_PASSWORD` | a long password (12+ chars); your login until you change it in Admin |
   | `ANTHROPIC_API_KEY` | your Claude API key (or paste it later in Admin → AI model) |
   | `DONNA_PUBLIC_URL` | your public URL, e.g. `https://donna-production.up.railway.app` |

   `DONNA_DATA=/data`, `DONNA_CLOUD=1` and `TZ=Asia/Kolkata` are already set in the Dockerfile.
4. **Settings → Networking → Generate domain**. Put that URL in `DONNA_PUBLIC_URL` and redeploy.
5. Keep **one replica** and the **restart policy "On failure"** (the default). A restore restarts Donna this way.

## Move your data from the Mac

1. On the Mac: **Admin → Data & appearance → Download full backup (.zip)**.
2. Stop the Mac copy (Ctrl-C in its terminal).
3. Open your cloud URL, sign in with `DONNA_ADMIN_PASSWORD`, go to **Admin → Data → Restore from backup…** and pick the zip.
   Donna restarts with all your goals, tasks, journal, vault and documents. Reload after ~20 seconds.
   If your Mac copy had its own app password, that password applies after the restore.
4. In **Admin → Login & hosting**, turn on **two-factor authentication**.

The backup contains your encrypted vault *and* the key for your integration secrets: delete the zip
from Downloads once the restore works.

## After moving

- **Google Calendar**: add `https://<your-domain>/api/google/callback` as an authorised redirect URI
  in Google Cloud Console, then reconnect in Admin.
- **Telegram, email, inbox triage**: work unchanged (they're in the restored settings).
- **Phone**: open the URL in Safari → Share → *Add to Home Screen*.
- **Backups**: download a full backup from Admin now and then. The volume is your only copy.

## Other hosts

The same image runs anywhere with a persistent disk:
- **Fly.io**: `fly launch` (no database), `fly volumes create donna_data --size 1`, mount it at `/data` in `fly.toml`, set the variables with `fly secrets set`.
- **Render**: Web Service (Docker) on a paid instance + a Disk mounted at `/data`.
- **Any VPS**: `docker build -t donna . && docker run -d --restart unless-stopped -p 8765:8765 -v donna-data:/data -e DONNA_ADMIN_PASSWORD=… -e DONNA_PUBLIC_URL=https://… -e ANTHROPIC_API_KEY=… donna`, behind Caddy/Nginx for HTTPS.
