# Deploying Donna to the cloud (24×7)

Donna is one container plus **one persistent volume** (database, encryption key, documents).
It needs an always-on host: the scheduler sends reminders, the Telegram bot long-polls, and
inbox scans run in the background. Serverless platforms (Vercel, Lambda) won't work.

> **Run exactly one instance.** Two copies of Donna (e.g. your Mac and the server) with the same
> Telegram bot would fight over messages and send every reminder twice. Stop the Mac copy once the
> server is live.

## Recommended: Railway (≈ US$5/month)

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
