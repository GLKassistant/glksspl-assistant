# GL Kundu & Sons Steel — Business Assistant

A web app where your parents can ask about inventory, customers, payments, and
sales in plain English, Hindi, or Bengali — and add new data through simple forms.

**The goal:** you set this up once from the US. After that, your parents just
open a web link on their phone or computer. Nothing for them to install or manage.

---

## How it works

```
You (US):       edit code → push to GitHub → auto-deploys to Render
Database:       Supabase (permanent free tier — your data is never deleted)
AI:             Claude API (key stays safe on the server)
Parents (Malda): open one web link → use the app
```

---

## What you need (all free to start)

1. A **GitHub** account — https://github.com  (sign up with your own email, region = your real location, e.g. United States)
2. A **Render** account — https://render.com  (sign up *with* GitHub — easiest)
3. A **Supabase** account — https://supabase.com  (your permanent database)
4. An **Anthropic API key** — https://console.anthropic.com → Settings → API Keys

---

## One-time setup (about 20 minutes)

### Step 1 — Put the code on GitHub
1. Create a new repository on GitHub named `glksspl-assistant`.
2. On the repo page: **Add file → Upload files** → drag in all these files → **Commit changes**.

### Step 2 — Create the database on Supabase
1. Supabase → **New Project**. Name it `glksspl`, set a database password (SAVE IT).
2. Region: **Mumbai** if available, otherwise **Singapore** — pick the one closest to Malda.
3. Wait ~2 minutes for it to finish.
4. Click **Connect** (top of the project) → copy the **Connection string** (URI / pooler).
5. In that string, replace `[YOUR-PASSWORD]` with the password you set. Keep it for Step 4.

### Step 3 — Deploy the app on Render
1. Render → **New → Web Service** → connect GitHub → pick `glksspl-assistant`.
2. Confirm:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Instance Type: **Free**
   - Region: **Singapore** (closest free region to India — matches your database)
3. Click **Create Web Service**.

### Step 4 — Add your secret keys
In the service → **Environment** tab, add three variables:
- `ANTHROPIC_API_KEY` → your Claude key
- `DATABASE_URL` → your full Supabase connection string from Step 2
- `CLAUDE_MODEL` → `claude-sonnet-4-20250514`

Click **Save Changes**. Render restarts the app automatically.

### Step 5 — Get the link & hand it off
1. Your live URL appears at the top, e.g. `https://glksspl-assistant.onrender.com`.
2. Test it: ask "Show me current inventory."
3. WhatsApp the link to your parents. On their phone:
   - **Android (Chrome):** menu (⋮) → **Add to Home screen**
   - **iPhone (Safari):** Share → **Add to Home Screen**

Done — there's now an app icon on their phone. They tap it and type in any language.

---

## Daily use

**Ask questions** → open the app, type or tap a quick question.

**Add data** → tap **+ Add Data** at the top:
- **Stock In** — when steel arrives from Tata Steel
- **New Sale** — records a sale and reduces stock automatically
- **Customer** — add a customer or record money owed

---

## Test on your own laptop first (optional)

```bash
pip install -r requirements.txt

# Mac/Linux:
export ANTHROPIC_API_KEY=sk-ant-your-key-here
# Windows PowerShell:
#   $env:ANTHROPIC_API_KEY="sk-ant-your-key-here"

python app.py
# open http://localhost:5000
```

With no DATABASE_URL set, it uses a local `steel.db` file with sample data, so you
can click around safely before going live. The same key data will appear once you
connect Supabase.

---

## Good to know

- **Region:** keep Render and Supabase in nearby regions (both Singapore, or DB in
  Mumbai) so the app stays fast for your parents.
- **Free Render tier sleeps** after 15 min idle — first visit then takes ~30s to wake.
  The $7/month tier removes this once they rely on it daily.
- **Sample data** seeds on first run so the app isn't empty. Replace it via Add Data.
- **Model:** change `CLAUDE_MODEL` in Render's Environment tab anytime to upgrade.

## Ideas to add later (just ask)
- WhatsApp input — update stock by sending a message
- Voice input in Hindi/Bengali
- Automatic payment reminders to customers
- Monthly sales/profit reports
- A family password so only you can open it
