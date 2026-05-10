# Session 4: Deploy to a Public URL

By the end of this session, you'll have a real website at something like
`https://mf-overlap-app.onrender.com` that anyone can visit.

Total time: ~25 minutes. Take it one part at a time.

---

## Part A: Install GitHub Desktop (~5 min)

GitHub Desktop is a friendly visual app for using GitHub — no command line needed.

1. Open your browser
2. Go to: **https://desktop.github.com**
3. Click the big purple **Download for Windows** button
4. Open the downloaded file (in your Downloads folder, named something like `GitHubDesktopSetup-x64.exe`)
5. The installer runs automatically — wait ~30 seconds for it to finish
6. GitHub Desktop opens. Click **Sign in to GitHub.com**
7. Your browser opens. Sign in with the GitHub account you created in Session 1
8. Click **Authorize desktop**
9. Back in GitHub Desktop, click **Configure Git** then **Finish** (defaults are fine)

### ✅ Verify
You should see a screen that says "Let's get started!" with options like "Create a New Repository" and "Add an Existing Repository". If you see this → ✅ done.

---

## Part B: Upload your project to GitHub (~5 min)

1. In GitHub Desktop, click **Add an Existing Repository from your Hard Drive**
2. Click **Choose...** and navigate to: `D:\Siddhant\MF Overlap App`
3. Click **Select Folder**
4. You'll see a warning: "This directory does not appear to be a Git repository." That's expected. Click the **create a repository** link in that warning.
5. A "Create a new repository" dialog opens. Fill in:
   - **Name:** `mf-overlap-app` (or whatever you like — lowercase, no spaces)
   - **Description:** `Mutual fund portfolio overlap analyzer`
   - **Local Path:** `D:\Siddhant` (it auto-fills, leave it)
   - **Initialize this repository with a README:** UNCHECK if checked (we already have one)
   - **Git Ignore:** None (we already have `.gitignore`)
   - **License:** None (or MIT if you like)
6. Click **Create Repository**

You're now in the main GitHub Desktop view showing your project.

7. At the bottom-left, you'll see a list of files with checkboxes — these are your changes.
8. In the bottom-left corner, type a **Summary** (commit message): `Initial commit`
9. Click the blue **Commit to main** button
10. Now click **Publish repository** at the top right
11. A dialog appears:
    - **Name:** `mf-overlap-app` (already filled)
    - **Description:** (already filled)
    - **Keep this code private:** Your choice. Public is fine since this is a portfolio project. Private if you'd rather.
12. Click **Publish Repository**

### ✅ Verify
1. Go to https://github.com in your browser
2. Click your profile picture (top right) → **Your repositories**
3. You should see `mf-overlap-app` in the list
4. Click it — you should see all your files: `app.py`, `static/index.html`, `Procfile`, etc.

If yes → ✅ done with Part B. Tell me **"GitHub done"** and we'll move to Part C.

---

## Part C: Deploy to Render (~10 min)

Render runs your app for free and gives you a public URL.

### Sign up

1. Go to: **https://render.com**
2. Click **Get Started** (top right)
3. Click **GitHub** to sign up with your GitHub account
4. Authorize Render to access your GitHub
5. You'll land on the Render dashboard

### Create the Web Service

1. Click the big **+ New** button → choose **Web Service**
2. You'll see "Connect a repository". Find `mf-overlap-app` and click **Connect**
   - If you don't see it: click "Configure GitHub App" → grant Render access to the repo → come back
3. A configuration page opens. Fill in:

| Field | Value |
|---|---|
| **Name** | `mf-overlap-app` (this becomes part of your URL) |
| **Region** | **Singapore** (closest to India for fast loading) |
| **Branch** | `main` (already filled) |
| **Root Directory** | (leave blank) |
| **Runtime** | `Python 3` (auto-detected) |
| **Build Command** | `pip install -r requirements.txt` (auto-filled) |
| **Start Command** | `gunicorn app:app --workers 2 --threads 4 --timeout 60` |
| **Instance Type** | **Free** (very important — don't pick paid by accident!) |

4. Scroll down and click **Create Web Service**

### Wait for the first build

Render now installs your dependencies and starts your app. You'll see a live log showing:
```
==> Cloning from https://github.com/.../mf-overlap-app
==> Using Python version 3.11.9
==> Installing dependencies...
   Successfully installed flask-3.0.0 flask-cors-4.0.0 gunicorn-21.2.0 ...
==> Starting service with 'gunicorn app:app ...'
==> Your service is live 🎉
```

This takes **3-5 minutes** the first time. Be patient.

### Get your URL

When you see "Your service is live", scroll to the top of the page. You'll see your URL — something like:
```
https://mf-overlap-app.onrender.com
```

### ✅ Verify
1. Click that URL (or paste it into Chrome)
2. You should see the MF Overlap Analyzer
3. The header pill should show "14,571 schemes · 51 AMCs · 2026-05"
4. Try searching for a fund name
5. Try the "Try sample portfolio" button

If it all works → ✅ **You're live!** 🎉

Send me your URL — I'll verify it works from my end too.

---

## Quirks to know about

**Cold start (~30s on first visit):**
Render's free tier puts your app to sleep if no one visits for 15 minutes. The next visit triggers a wake-up, which takes ~30 seconds. Subsequent visits are fast. If this becomes annoying, the paid plan ($7/mo) keeps it always-on.

**Auto-deploy on changes:**
From now on, whenever we make code changes in future sessions, you'll commit them via GitHub Desktop and click "Push origin". Render auto-detects the push and redeploys in ~3 minutes. No manual deployment ever again.

**Custom domain (later):**
Want `mfoverlap.in` instead of `mf-overlap-app.onrender.com`? We can add a custom domain in Session 5 — costs ~₹700/year for the domain.

---

## Troubleshooting

**"Build failed"**
Look at the live log. Most common issue: a typo in `requirements.txt`. Share the log with Claude.

**"Application failed to respond"**
Usually a typo in the Start Command. Should be exactly: `gunicorn app:app --workers 2 --threads 4 --timeout 60`

**Site loads but shows "Connection error"**
The MFData.in API might be down, or Render's outbound network has a hiccup. Refresh in 30 seconds.

**Anything else weird**
Send me what you see — log text or screenshots. We'll fix it.
