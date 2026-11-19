import csv
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import requests
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
GOOGLE_HOST = re.compile(r"(?:www\.)?google\.(?:com|[a-z]{2}|(?:com|co)\.[a-z]{2})")
TRUNCATED_TITLE = re.compile(r"(?:\.{3}|…)\s*$")
PAGE_PLACEHOLDERS = {"access denied", "just a moment", "please wait", "verify you are human"}


def publisher_url(result):
    goto_links = []
    for field in ("link", "redirect_link"):
        value = (result.get(field) or "").strip()
        try:
            parsed = urlsplit(value)
            is_google = not parsed.netloc or GOOGLE_HOST.fullmatch(parsed.hostname or "")
            if is_google and parsed.path in ("/url", "/goto"):
                query = parse_qs(parsed.query)
                target = (query.get("url") or query.get("q") or [""])[0]
                if parsed.path == "/goto" and not target.startswith(("http://", "https://")):
                    if not parsed.netloc:
                        value = f"https://www.google.com{value}"
                    if value not in goto_links:
                        goto_links.append(value)
                value = target
                parsed = urlsplit(value)
            if parsed.scheme in ("http", "https") and parsed.hostname:
                if not (GOOGLE_HOST.fullmatch(parsed.hostname) and parsed.path in ("/url", "/goto")):
                    return value
        except ValueError:
            continue

    for link in goto_links:
        try:
            with requests.get(link, timeout=(3, 5), stream=True) as page:
                destination = urlsplit(page.url)
                if (
                    destination.scheme in ("http", "https")
                    and destination.hostname
                    and not GOOGLE_HOST.fullmatch(destination.hostname)
                ):
                    return page.url
        except (requests.RequestException, ValueError):
            continue
    return ""


class PageTitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.title_parts = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            attributes = dict(attrs)
            name = attributes.get("property") or attributes.get("name")
            content = attributes.get("content")
            if name in ("og:title", "twitter:title") and content:
                self.metadata.setdefault(name, content)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, text):
        if self.in_title:
            self.title_parts.append(text)


def full_headline(google_title, url):
    if not url or (
        google_title
        and not TRUNCATED_TITLE.search(google_title)
        and not google_title.startswith(("https://", "http://"))
    ):
        return google_title

    try:
        with requests.get(url, timeout=(3, 5), stream=True) as page:
            page.raise_for_status()
            if "html" not in page.headers.get("Content-Type", "").lower():
                return google_title
            head = bytearray()
            for chunk in page.iter_content(chunk_size=8192):
                head.extend(chunk)
                if b"</head" in head.lower() or len(head) >= 256 * 1024:
                    break
            parser = PageTitleParser()
            encoding = page.encoding
            if not encoding or encoding.lower() == "iso-8859-1":
                encoding = "utf-8"
            parser.feed(head.decode(encoding, errors="replace"))
    except (requests.RequestException, LookupError):
        return google_title

    for candidate in (
        parser.metadata.get("og:title", ""),
        parser.metadata.get("twitter:title", ""),
        "".join(parser.title_parts),
    ):
        headline = " ".join(candidate.split())
        if (
            headline
            and headline.lower().rstrip(".!…") not in PAGE_PLACEHOLDERS
            and not TRUNCATED_TITLE.search(headline)
        ):
            return headline
    return google_title


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

        url = publisher_url(result)
        rows.append({
            "Original Title": title,
            "Original Published Date": release_date.isoformat() if release_date else "",
            "Media Outlet": result.get("source") or urlsplit(url).hostname or "",
            "Result Title": full_headline(result.get("title") or "", url),
            "Result Published Date": result_date.isoformat() if result_date else displayed_date,
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
