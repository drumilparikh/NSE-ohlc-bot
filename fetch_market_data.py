"""
Daily Nifty 50 & Sensex OHLC report, with a persistent running history.

On first run (no data/history.csv yet) it backfills ~5 years of daily OHLC
for Nifty 50 (^NSEI) and Sensex (^BSESN) from Yahoo Finance. On every run
after that, it just fetches the latest day and appends it to the history.

The daily email contains two sheets:
    "Today"   - just that day's OHLC
    "History" - the full running log to date

Designed to run unattended on GitHub Actions. Reads credentials from
environment variables (set as GitHub Actions secrets):
    SENDER_EMAIL          - Gmail address used to send the report
    SENDER_APP_PASSWORD   - Gmail App Password (NOT your normal password)
    RECIPIENT_EMAIL       - where the report should land

The workflow commits data/history.csv back to the repo after each run so
the history persists across runs (GitHub Actions containers are ephemeral).
"""

import os
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import yfinance as yf

TICKERS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
}

HISTORY_PATH = "data/history.csv"
BACKFILL_PERIOD = "5y"
HISTORY_COLUMNS = ["Index", "Date", "Open", "High", "Low", "Close"]


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def load_history() -> pd.DataFrame:
    if os.path.exists(HISTORY_PATH):
        df = pd.read_csv(HISTORY_PATH, dtype={"Date": str})
        return df[HISTORY_COLUMNS]
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def save_history(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    df.sort_values(["Index", "Date"]).to_csv(HISTORY_PATH, index=False)


def fetch_backfill() -> pd.DataFrame:
    """Pull ~5 years of daily OHLC for both indices (one-time, first run only)."""
    frames = []
    for name, ticker in TICKERS.items():
        df = yf.download(
            ticker, period=BACKFILL_PERIOD, interval="1d",
            progress=False, auto_adjust=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            raise ValueError(f"No backfill data returned for {name} ({ticker})")

        df = df.reset_index()[["Date", "Open", "High", "Low", "Close"]]
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = df[col].astype(float).round(2)
        df["Index"] = name
        frames.append(df[HISTORY_COLUMNS])

    return pd.concat(frames, ignore_index=True)


def fetch_latest() -> dict:
    """Fetch the most recent daily OHLC row for each index."""
    end = datetime.now()
    start = end - timedelta(days=10)  # buffer for weekends/holidays

    data = {}
    for name, ticker in TICKERS.items():
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval="1d", progress=False, auto_adjust=False,
        )
        df = _flatten_columns(df)
        if df.empty:
            raise ValueError(f"No data returned for {name} ({ticker})")

        latest = df.iloc[-1]
        data[name] = {
            "Date": df.index[-1].strftime("%Y-%m-%d"),
            "Open": round(float(latest["Open"]), 2),
            "High": round(float(latest["High"]), 2),
            "Low": round(float(latest["Low"]), 2),
            "Close": round(float(latest["Close"]), 2),
        }
    return data


def update_history(history: pd.DataFrame, latest: dict) -> pd.DataFrame:
    new_rows = pd.DataFrame([{"Index": name, **vals} for name, vals in latest.items()])
    combined = pd.concat([history, new_rows], ignore_index=True)
    combined = combined.drop_duplicates(subset=["Index", "Date"], keep="last")
    return combined.sort_values(["Index", "Date"]).reset_index(drop=True)


def build_excel(today_data: dict, history: pd.DataFrame, filepath: str) -> str:
    """One Today sheet and one History sheet per index (4 sheets total)."""
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        for name in TICKERS:  # preserves NIFTY 50, SENSEX order
            today_df = pd.DataFrame([today_data[name]])[["Date", "Open", "High", "Low", "Close"]]
            today_df.to_excel(writer, index=False, sheet_name=f"{name} - Today"[:31])

            hist_df = (
                history[history["Index"] == name]
                .sort_values("Date")[["Date", "Open", "High", "Low", "Close"]]
            )
            hist_df.to_excel(writer, index=False, sheet_name=f"{name} - History"[:31])
    return filepath


def send_email(filepath: str, report_date: str, history_rows: int) -> None:
    sender = os.environ["SENDER_EMAIL"]
    password = os.environ["SENDER_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"Nifty 50 & Sensex OHLC Report - {report_date}"

    body = (
        f"Attached: Nifty 50 and Sensex OHLC for {report_date}.\n\n"
        f"Sheets: NIFTY 50 - Today / NIFTY 50 - History / "
        f"SENSEX - Today / SENSEX - History ({history_rows} rows of history to date)\n\n"
        "Auto-generated daily by GitHub Actions. Source: Yahoo Finance (delayed)."
    )
    msg.attach(MIMEText(body, "plain"))

    with open(filepath, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition", f"attachment; filename={os.path.basename(filepath)}"
    )
    msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def main():
    history = load_history()

    if history.empty:
        print("No existing history found - running one-time 5-year backfill...")
        history = fetch_backfill()
        save_history(history)  # save immediately in case the rest of the run fails
        print(f"Backfill complete: {len(history)} rows.")

    latest = fetch_latest()
    history = update_history(history, latest)
    save_history(history)

    report_date = max(v["Date"] for v in latest.values())
    filename = f"market_ohlc_{report_date}.xlsx"
    build_excel(latest, history, filename)
    send_email(filename, report_date, len(history))

    print(f"Report for {report_date} sent. History now has {len(history)} rows.")


if __name__ == "__main__":
    main()
