import csv
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pandas as pd
import streamlit as st
from serpapi import GoogleSearch


TAIPEI = timezone(timedelta(hours=8))
OUTPUT_COLUMNS = [
    "Original Title",
    "Original Published Date",
    "Media Outlet",
    "Result Title",
    "Result Published Date",
    "URL",
]
RELATIVE_DATE = re.compile(
    r"(\d+)\s+(minute|hour|day|week)s?\s+ago", re.IGNORECASE
)
OTHER_RELATIVE_DATE = re.compile(r"\bago\b", re.IGNORECASE)
RELATIVE_UNITS = {
    "minute": "minutes",
    "hour": "hours",
    "day": "days",
    "week": "weeks",
}


def parse_calendar_date(value):
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def result_date_for_comparison(value, searched_at):
    label = value.strip()
    relative = RELATIVE_DATE.fullmatch(label)
    if relative:
        amount, unit = relative.groups()
        elapsed = timedelta(**{RELATIVE_UNITS[unit.lower()]: int(amount)})
        return (searched_at - elapsed).date()
    if label.lower() == "yesterday":
        return searched_at.date() - timedelta(days=1)
    if label.lower() == "today":
        return searched_at.date()
    # Coarse labels such as "2 months ago" do not give a calendar date.
    if OTHER_RELATIVE_DATE.search(label):
        return None
    return parse_calendar_date(label)


def search_release(title, release_date, api_key):
    response = GoogleSearch({
        "engine": "google",
        "q": title,
        "api_key": api_key,
    }).get_dict()
    if response.get("error"):
        raise RuntimeError(response["error"])

    created_at = (response.get("search_metadata") or {}).get("created_at")
    timestamp = pd.to_datetime(created_at, errors="coerce", utc=True)
    searched_at = (
        datetime.now(TAIPEI)
        if pd.isna(timestamp)
        else timestamp.astimezone(TAIPEI)
    )

    rows = []
    for result in response.get("organic_results", []):
        displayed_date = result.get("date") or ""
        result_date = result_date_for_comparison(displayed_date, searched_at)
        if release_date and result_date and result_date < release_date:
            continue

        url = result.get("link") or ""
        rows.append({
            "Original Title": title,
            "Original Published Date": release_date.isoformat() if release_date else "",
            "Media Outlet": result.get("source") or urlsplit(url).hostname or "",
            "Result Title": result.get("title") or "",
            "Result Published Date": displayed_date,
            "URL": url,
        })

    return rows


def main():
    st.set_page_config(page_title="Media Pickup Search", layout="wide")
    st.title("Media Pickup Search")
    api_key = st.sidebar.text_input("SerpApi key", type="password").strip()
    uploaded_file = st.file_uploader(
        "Upload a CSV with Title and Published Date (or Date)", type=["csv"]
