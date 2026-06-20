# Daily Nifty 50 / Sensex OHLC Email Report (with running history)

Runs automatically on GitHub's servers, Mon-Fri at 4:00 PM IST (after market
close). Your laptop never needs to be on.

## What it does
1. **First run only:** backfills ~5 years of daily OHLC for Nifty 50
   (`^NSEI`) and Sensex (`^BSESN`) from Yahoo Finance into
   `data/history.csv`.
2. **Every run:** fetches the latest day's OHLC, appends it to the history
   log (safe to re-run the same day — it won't duplicate), and commits the
   updated `data/history.csv` back to the repo so the log persists.
3. Emails an Excel file with two sheets:
   - **Today** — just that day's OHLC
   - **History** — the full running log to date
4. Sends it via Gmail SMTP.

## One-time setup (~10 minutes)

### 1. Create a GitHub repo
Create a new **private** repo (e.g. `market-ohlc-report`) and upload these
files, keeping the folder structure:
```
market-ohlc-report/
├── fetch_market_data.py
├── requirements.txt
└── .github/workflows/daily_market_report.yml
```
(`data/history.csv` doesn't need to exist yet — the script creates it on
first run.)

### 2. Allow the workflow to write to the repo
Go to **Settings → Actions → General → Workflow permissions** and select
**"Read and write permissions"**. This lets the workflow commit the updated
history log back to the repo after each run. (The workflow file also
declares `permissions: contents: write`, but this repo-level setting needs
to be enabled too on some accounts.)

### 3. Create a Gmail App Password (the sender account)
Regular Gmail passwords won't work for SMTP. You need an App Password:
1. Turn on 2-Step Verification on the sending Gmail account, if not already
   on: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Create a new app password (name it anything, e.g. "market-report-bot").
4. Copy the 16-character password — you'll only see it once.

*(If you'd rather not use your main Gmail, create a free throwaway Gmail
account just for sending this report.)*

### 4. Add repo secrets
In your GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add three:

| Name | Value |
|---|---|
| `SENDER_EMAIL` | the Gmail address sending the report |
| `SENDER_APP_PASSWORD` | the 16-character app password from step 3 |
| `RECIPIENT_EMAIL` | where you want the report delivered |

### 5. Test it manually
Go to the **Actions** tab → "Daily Market OHLC Report" → **Run workflow**.
This first run will take a little longer since it's doing the 5-year
backfill. Check the run logs, check the recipient inbox, and confirm
`data/history.csv` appeared in the repo afterward.

### 6. Let it run
Once the manual test succeeds, it'll fire automatically every weekday at
4:00 PM IST, appending one new row per index per day to the history.

## Notes & caveats
- **Data is from Yahoo Finance**, not the official NSE/BSE feed — reliable
  and free, but can lag the official close by a few minutes and
  occasionally differs by a fraction of a point from NSE's own numbers. If
  you ever need official, audit-grade data, NSE/BSE have separate paid data
  feeds.
- **The history lives in the repo**, not in your email — `data/history.csv`
  is the source of truth, committed by the workflow itself (via the
  `github-actions[bot]` account). The email is just a convenient delivered
  copy each day.
- **Growth over time:** ~2 rows/day (one per index) → roughly 500 rows/year.
  After 5+ years that's only a few thousand rows, trivial for Excel/email
  attachment size.
- **GitHub Actions cron isn't second-precise** — it can fire a few minutes
  late under load. Fine for an end-of-day report.
- **Market holidays:** the script always grabs the *most recent* trading
  day, so on a closed-market day it'll resend the last session's numbers in
  the "Today" sheet — but since the date is unchanged, it won't create a
  duplicate row in History.
