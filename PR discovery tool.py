
import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import io
import re


# --- Helper: Parse dates for display only ---
# Dates are NOT used to filter search results.

def parse_date(value):
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if not text:
        return ""

    # Handle relative dates returned by Google
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

        return result.date().isoformat()

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        # Preserve Google's original date text
        return text

    return parsed.date().isoformat()


# --- UI Setup ---

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
This tool searches Google for third-party media coverage
using the original press release title.

1. Enter your SerpApi Key.
2. Upload a CSV containing **Title** and **Published Date**.
3. Download the media coverage report.

**Note:** No publication-date filtering is applied.
""")


# --- Sidebar ---

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

    df_input = pd.read_csv(uploaded_file)

    # Normalize column names
    df_input.columns = [
        str(column).strip()
        for column in df_input.columns
    ]

    # Accept Published Date or Date
    date_column = next(
        (
            column for column in df_input.columns
            if column.lower() in ["published date", "date"]
        ),
        None
    )

    if "Title" not in df_input.columns:
        st.error(
            "Error: CSV must contain a column named 'Title'"
        )

    elif date_column is None:
        st.error(
            "Error: CSV must contain 'Published Date' or 'Date'"
        )

    else:
        st.success("CSV Loaded Successfully!")

        if st.button("Start Discovery Process"):

            results_storage = []

            # Keep Code 1's title selection logic
            search_items = df_input[
                df_input["Title"].notna()
            ]

            progress_bar = st.progress(0)
            status_text = st.empty()

            total = len(search_items)

            if total == 0:
                st.info("No valid titles found.")
                st.stop()

            for i, (_, row) in enumerate(
                search_items.iterrows()
            ):

                title = str(row["Title"]).strip()

                original_date = parse_date(
                    row[date_column]
                )

                status_text.text(
                    f"Searching ({i+1}/{total}): "
                    f"{title[:50]}..."
                )

                # EXACT SAME SEARCH QUERY AS CODE 1
                query = f'"{title.strip()} "'

                # EXACT SAME GOOGLE SEARCH SETTINGS
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

                    results = search.get_dict().get(
                        "organic_results", []
                    )

                    for res in results:

                        link = res.get("link", "")

                        # SAME DOMAIN EXCLUSION AS CODE 1
                        if not any(
                            domain.strip() in link
                            for domain in exclude_list
                            if domain.strip()
                        ):

                            # Date collected for output only
                            result_date = parse_date(
                                res.get("date")
                            )

                            results_storage.append({
                                "Original Title": title,
                                "Original Published Date": original_date,
                                "Media Outlet": res.get("source", ""),
                                "Result Title": res.get("title", ""),
                                "Result Published Date": result_date,
                                "URL": link
                            })

                except Exception as e:
                    st.warning(
                        f"Search failed for {title}: {e}"
                    )

                progress_bar.progress(
                    (i + 1) / total
                )

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

                st.write(
                    f"Total discovered results: "
                    f"{len(df_results)}"
                )

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
                    "No third-party media found "
                    "based on the domain filters."
                )

elif not api_key and uploaded_file:
    st.info(
        "Please enter your SerpApi Key "
        "in the sidebar to begin."
    )
