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
    )
    if uploaded_file is None:
        st.session_state.pop("pickup_report", None)
        return

    file_bytes = uploaded_file.getvalue()
    try:
        csv_text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(csv_text.splitlines(keepends=True))
        columns = {name.strip().lower(): name for name in reader.fieldnames or []}
        title_column = columns.get("title")
        date_column = columns.get("published date") or columns.get("date")
        if title_column is None or date_column is None:
            st.error("The CSV needs a Title column and a Published Date or Date column.")
            return
        releases = [
            (row[title_column].strip(), row.get(date_column))
            for row in reader
            if row.get(title_column) and row[title_column].strip()
        ]
    except (UnicodeError, csv.Error):
        st.error("Upload a valid UTF-8 CSV.")
        return

    if not releases:
        st.info("The CSV has no press release titles.")
        return

    if st.button("Find media pickup", disabled=not api_key):
        rows = []
        warnings = []
        progress = st.progress(0)
        for index, (title, date_text) in enumerate(releases, start=1):
            release_date = parse_calendar_date(date_text)
            if release_date is None:
                warnings.append(f"Missing or invalid release date for {title}. All results were kept.")
            try:
                rows.extend(search_release(title, release_date, api_key))
            except Exception:
                warnings.append(f"Google search failed for {title} (search {index}).")
            progress.progress(index / len(releases))
        progress.empty()
        st.session_state["pickup_report"] = (file_bytes, rows, warnings)

    report = st.session_state.get("pickup_report")
    if report is None or report[0] != file_bytes:
        return

    _, rows, warnings = report
    for message in warnings:
        st.warning(message)
    if not rows:
        st.info("No media results to display.")
        return

    results = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    st.dataframe(results, hide_index=True)
    st.download_button(
        "Download media coverage CSV",
        data=results.to_csv(index=False).encode("utf-8-sig"),
        file_name="Media_Coverage_Report.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
