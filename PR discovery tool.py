import io
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
from serpapi import GoogleSearch


# --- Helpers ---

class PageTitleParser(HTMLParser):
    """Read a page's Open Graph, Twitter, or HTML title."""

    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.meta_title = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag.lower() == "meta":
            property_name = (
                attrs.get("property") or attrs.get("name") or ""
            ).lower()

            if property_name in {"og:title", "twitter:title"}:
                self.meta_title = attrs.get("content", "").strip()

        elif tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)


def get_full_page_title(url):
    """Try to get a fuller title from the linked page."""
    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urlopen(request, timeout=5) as response:
            html = response.read(1_000_000).decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace"
            )

        parser = PageTitleParser()
        parser.feed(html)

        if parser.meta_title:
            return parser.meta_title

        return " ".join(" ".join(parser.title_parts).split())

    except Exception:
        return ""


def parse_result_date(value):
    """Parse Google dates, including values such as '3 days ago'."""
    if not value:
        return None

    text = str(value).strip()

    relative_match = re.search(
        r"(\d+)\s+"
        r"(minute|hour|day|week|month|year)s?\s+ago",
        text,
        flags=re.IGNORECASE
    )

    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()

        days_per_unit = {
            "minute": 0,
            "hour": 0,
            "day": 1,
            "week": 7,
            "month": 30,
            "year": 365,
        }

        hours_per_unit = {
            "minute": 1 / 60,
            "hour": 1,
        }

        if unit in hours_per_unit:
            result_datetime = datetime.now() - timedelta(
                hours=amount * hours_per_unit[unit]
            )
        else:
            result_datetime = datetime.now() - timedelta(
                days=amount * days_per_unit[unit]
            )

        return result_datetime.date()

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return None

    return parsed.date()


# --- UI Setup ---

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
Upload a CSV with a **Title** column and a **Date** or **Published Date**
column. The tool searches Google for coverage published after the original
press release date.
""")


# --- Sidebar: Settings ---

with st.sidebar:
    st.header("Settings")

    api_key = st.text_input(
        "Enter your SerpApi Key",
        type="password"
    )

    exclude_domains = st.text_area(
        "Domains to Exclude (one per line)",
        value=(
            "newswise.com\n"
            "youtube.com\n"
            "facebook.com\n"
            "linkedin.com\n"
            "twitter.com\n"
            "x.com"
        )
    )

    exclude_list = [
        domain.strip().lower()
        for domain in exclude_domains.splitlines()
        if domain.strip()
    ]

    st.caption("The search is limited to two Google results pages per title.")


# --- File Upload ---

uploaded_file = st.file_uploader(
    "Upload your Input_PR_Titles.csv",
    type=["csv"]
)


# --- Main Logic ---

if uploaded_file and api_key:
    try:
        df_input = pd.read_csv(uploaded_file)
        df_input.columns = [
            str(column).strip()
            for column in df_input.columns
        ]

    except Exception as e:
        st.error(f"Unable to read CSV: {e}")
        st.stop()

    # Find the input date column, accepting either requested name.
    date_columns = {
        str(column).strip().lower(): column
        for column in df_input.columns
    }

    input_date_column = (
        date_columns.get("published date")
        or date_columns.get("date")
    )

    if "Title" not in df_input.columns:
        st.error("CSV must contain a column named 'Title'.")

    elif input_date_column is None:
        st.error(
            "CSV must contain a date column named 'Date' "
            "or 'Published Date'."
        )

    else:
        st.success(
            f"CSV loaded successfully — {len(df_input)} rows found."
        )

        if st.button("Start Discovery Process"):
            search_items = []
            skipped_rows = 0

            for _, row in df_input.iterrows():
                title = str(row.get("Title", "")).strip()

                if not title or title.lower() == "nan":
                    continue

                original_date = parse_result_date(row[input_date_column])

                if original_date is None:
                    skipped_rows += 1
                    continue

                search_items.append((title, original_date))

            if skipped_rows:
                st.warning(
                    f"Skipped {skipped_rows} row(s) with a missing "
                    "or unrecognized publication date."
                )

            if not search_items:
                st.warning(
                    "No rows with a valid title and publication date were found."
                )
                st.stop()

            results_storage = []
            seen_results = set()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (title, original_date) in enumerate(search_items):
                status_text.text(
                    f"Searching ({i + 1}/{len(search_items)}): "
                    f"{title[:50]}..."
                )

                # Ask Google to prioritize results after the original date.
                query = (
                    f'"{title}" after:{original_date.isoformat()}'
                )

                # Search up to two Google results pages.
                for page in range(2):
                    params = {
                        "engine": "google",
                        "q": query,
                        "hl": "en",
                        "filter": "0",
                        "sort": "date",
                        "num": 10,
                        "start": page * 10,
                        "api_key": api_key,
                    }

                    try:
                        response = GoogleSearch(params).get_dict()
                        
                        error_message = str(response.get("error") or "")
                        
                        # Google may return this message when a page has no more results.
                        if "hasn't returned any results" in error_message.lower():
                            break
                        
                        if error_message:
                            st.warning(
                                f"Search failed for '{title}' "
                                f"(page {page + 1}): {error_message}"
                            )
                            continue
                        
                        organic_results = response.get("organic_results", [])
                        
                        # An empty result list is also a normal end to pagination.
                        if not organic_results:
                            break

                        for result in organic_results:
                            link = (result.get("link") or "").strip()

                            if not link:
                                continue

                            # Exclude specified domains.
                            link_lower = link.lower()
                            if any(
                                domain in link_lower
                                for domain in exclude_list
                            ):
                                continue

                            # Require a result date later than the PR date.
                            result_date = parse_result_date(
                                result.get("date")
                            )

                            if result_date is None or result_date <= original_date:
                                continue

                            # Avoid duplicate URLs for the same PR title.
                            result_key = (title.casefold(), link_lower)

                            if result_key in seen_results:
                                continue

                            seen_results.add(result_key)

                            google_title = (
                                result.get("title") or ""
                            ).strip()

                            full_page_title = get_full_page_title(link)
                            result_title = full_page_title or google_title

                            results_storage.append({
                                "Original Title": title,
                                "Original Published Date": (
                                    original_date.isoformat()
                                ),
                                "Media Outlet": (
                                    result.get("source")
                                    or result.get("displayed_link")
                                    or ""
                                ),
                                "Result Title": result_title,
                                "Result Published Date": (
                                    result_date.isoformat()
                                ),
                                "URL": link,
                            })

                    except Exception as e:
                        st.warning(
                            f"Search failed for '{title}' "
                            f"(page {page + 1}): {e}"
                        )

                progress_bar.progress(
                    (i + 1) / len(search_items)
                )

            status_text.empty()

            output_columns = [
                "Original Title",
                "Original Published Date",
                "Media Outlet",
                "Result Title",
                "Result Published Date",
                "URL",
            ]

            df_results = pd.DataFrame(
                results_storage,
                columns=output_columns
            )

            if not df_results.empty:
                st.subheader("Discovery Results")
                st.write(f"Found **{len(df_results)} results**.")

                st.dataframe(
                    df_results,
                    use_container_width=True
                )

                csv_buffer = io.StringIO()
                df_results.to_csv(
                    csv_buffer,
                    index=False,
                    encoding="utf-8-sig"
                )

                st.download_button(
                    label="📥 Download Media_Coverage_Report.csv",
                    data=csv_buffer.getvalue(),
                    file_name="Media_Coverage_Report.csv",
                    mime="text/csv"
                )

            else:
                st.info(
                    "No results with a Google-reported date later than "
                    "the original press release date were found."
                )

elif uploaded_file and not api_key:
    st.info("Please enter your SerpApi Key in the sidebar to begin.")
