import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import io
import re


# --- Helper: Parse dates ---

def parse_date(value):
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    # Handle relative dates returned by Google, such as "3 days ago"
    relative_match = re.search(
        r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago",
        text,
        flags=re.IGNORECASE
    )

    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()

        if unit == "minute":
            result = pd.Timestamp.now() - pd.Timedelta(minutes=amount)
        elif unit == "hour":
            result = pd.Timestamp.now() - pd.Timedelta(hours=amount)
        else:
            days_per_unit = {
                "day": 1,
                "week": 7,
                "month": 30,
                "year": 365
            }
            result = pd.Timestamp.now() - pd.Timedelta(
                days=amount * days_per_unit[unit]
            )

        return result.date()

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return None

    return parsed.date()


# --- UI Setup (English Interface) ---

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
This tool searches Google for third-party media coverage published after
the original press release date.
""")


# --- Sidebar: User Credentials ---

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
            "twitter.com"
        )
    )

    exclude_list = exclude_domains.split("\n")


# --- Main Logic ---

uploaded_file = st.file_uploader(
    "Upload your Input_PR_Titles.csv",
    type=["csv"]
)

if uploaded_file and api_key:
    # Read CSV
    df_input = pd.read_csv(uploaded_file)

    # Normalize column names
    df_input.columns = [str(column).strip() for column in df_input.columns]

    # Accept either "Published Date" or "Date"
    date_column = next(
        (
            column for column in df_input.columns
            if column.lower() in ["published date", "date"]
        ),
        None
    )

    if "Title" not in df_input.columns:
        st.error("Error: CSV must contain a column named 'Title'")

    elif date_column is None:
        st.error(
            "Error: CSV must contain a 'Published Date' or 'Date' column"
        )

    else:
        st.success("CSV Loaded Successfully!")

        if st.button("Start Discovery Process"):
            results_storage = []
            search_items = []
            skipped_rows = 0

            for _, row in df_input.iterrows():
                title = str(row["Title"]).strip()

                if not title or title.lower() == "nan":
                    continue

                original_date = parse_date(row[date_column])

                if original_date is None:
                    skipped_rows += 1
                    continue

                search_items.append((title, original_date))

            if skipped_rows:
                st.warning(
                    f"Skipped {skipped_rows} row(s) with a missing "
                    "or unreadable publication date."
                )

            if not search_items:
                st.info(
                    "No rows with a valid title and publication date."
                )
                st.stop()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (title, original_date) in enumerate(search_items):
                status_text.text(
                    f"Searching ({i + 1}/{len(search_items)}): "
                    f"{title[:50]}..."
                )

                # Newswise Formula: "Title "
                query = f'"{title.strip()} "'

                params = {
                    "engine": "google",
                    "q": query,
                    "hl": "en",
                    "filter": "0",
                    "sort": "date",
                    "api_key": api_key
                }

                try:
                    search = GoogleSearch(params)
                    response = search.get_dict()

                    error_message = str(response.get("error") or "")

                    # No results for a query is a normal outcome.
                    if (
                        "hasn't returned any results"
                        in error_message.lower()
                    ):
                        results = []
                    elif error_message:
                        st.warning(
                            f"Search failed for {title}: {error_message}"
                        )
                        results = []
                    else:
                        results = response.get("organic_results", [])

                    for res in results:
                        link = res.get("link", "")

                        if not link:
                            continue

                        excluded = any(
                            domain.strip().lower() in link.lower()
                            for domain in exclude_list
                            if domain.strip()
                        )

                        if excluded:
                            continue

                        result_date = parse_date(res.get("date"))

                        # Include only results published after the original post.
                        if result_date is None or result_date <= original_date:
                            continue

                        results_storage.append({
                            "Original Title": title,
                            "Original Published Date": (
                                original_date.isoformat()
                            ),
                            "Media Outlet": res.get("source", ""),
                            "Result Title": res.get("title", ""),
                            "Result Published Date": (
                                result_date.isoformat()
                            ),
                            "URL": link
                        })

                except Exception as e:
                    st.warning(f"Search failed for {title}: {e}")

                progress_bar.progress((i + 1) / len(search_items))

            status_text.empty()

            # --- Results Display & Download ---

            columns = [
                "Original Title",
                "Original Published Date",
                "Media Outlet",
                "Result Title",
                "Result Published Date",
                "URL"
            ]

            if results_storage:
                df_results = pd.DataFrame(
                    results_storage,
                    columns=columns
                )

                st.subheader("Discovery Results")
                st.dataframe(df_results)

                # Convert to CSV for download
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
                    "No third-party media results published after the "
                    "original press release date were found."
                )

elif not api_key and uploaded_file:
    st.info("Please enter your SerpApi Key in the sidebar to begin.")
