
import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import io
import re


# ============================================
# HELPER: PARSE PUBLICATION DATES
# ============================================

def parse_date(value):
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    # Handle Google's relative dates, e.g. "3 days ago"
    relative_match = re.search(
        r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago",
        text,
        flags=re.IGNORECASE
    )

    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()

        now = pd.Timestamp.now()

        if unit == "minute":
            result = now - pd.Timedelta(minutes=amount)
        elif unit == "hour":
            result = now - pd.Timedelta(hours=amount)
        else:
            days_per_unit = {
                "day": 1,
                "week": 7,
                "month": 30,
                "year": 365
            }

            result = now - pd.Timedelta(
                days=amount * days_per_unit[unit]
            )

        return result.date()

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return None

    return parsed.date()


# ============================================
# UI SETUP
# ============================================

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("PR Media Discovery Tool")

st.markdown("""
This tool discovers third-party media coverage through Google.

**Process:**
1. Search using the complete original press release title.
2. Collect all Google search results.
3. Exclude specified domains.
4. Remove results published before the original press release.
5. Export the media coverage report.

Same-day and undated results are retained.
""")


# ============================================
# SIDEBAR SETTINGS
# ============================================

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


# ============================================
# INPUT CSV
# ============================================

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

    # Accept either Published Date or Date
    date_column = next(
        (
            column
            for column in df_input.columns
            if column.lower() in ["published date", "date"]
        ),
        None
    )

    if "Title" not in df_input.columns:

        st.error(
            "Error: CSV must contain a column named 'Title'."
        )

    elif date_column is None:

        st.error(
            "Error: CSV must contain a 'Published Date' "
            "or 'Date' column."
        )

    else:

        st.success("CSV Loaded Successfully!")

        if st.button("Start Discovery Process"):

            # ====================================
            # STEP 1: SEARCH AND COLLECT
            #
            # Only the original title is used.
            # No publication-date filtering here.
            # ====================================

            all_results = []

            titles = df_input["Title"].dropna().tolist()

            if not titles:
                st.info("No titles found in the CSV.")
                st.stop()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, title in enumerate(titles):

                title = str(title).strip()

                status_text.text(
                    f"Searching ({i + 1}/{len(titles)}): "
                    f"{title[:50]}..."
                )

                # EXACT SAME SEARCH QUERY AS CODE 1
                query = f'"{title.strip()} "'

                # EXACT SAME SEARCH PARAMETERS
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

                    error_message = str(
                        response.get("error") or ""
                    )

                    if error_message:
                        st.warning(
                            f"Search issue for {title}: "
                            f"{error_message}"
                        )
                        results = []
                    else:
                        results = response.get(
                            "organic_results", []
                        )

                    # Collect all returned results
                    for res in results:

                        link = res.get("link", "")

                        all_results.append({
                            "Original Title": title,
                            "Media Outlet": res.get(
                                "source", ""
                            ),
                            "Result Title": res.get(
                                "title", ""
                            ),
                            "Result Published Date": res.get(
                                "date", ""
                            ),
                            "URL": link
                        })

                except Exception as e:

                    st.warning(
                        f"Search failed for {title}: {e}"
                    )

                progress_bar.progress(
                    (i + 1) / len(titles)
                )

            status_text.empty()

            # ====================================
            # STEP 2: EXCLUDE SPECIFIED DOMAINS
            # ====================================

            domain_filtered_results = []

            for result in all_results:

                link = result["URL"]

                excluded = any(
                    domain.strip().lower() in link.lower()
                    for domain in exclude_list
                    if domain.strip()
                )

                if not excluded:
                    domain_filtered_results.append(result)

            # ====================================
            # STEP 3: PUBLICATION DATE FILTER
            #
            # Date is used ONLY after collection.
            # Remove only earlier publications.
            # ====================================

            date_lookup = {}

            for _, row in df_input.iterrows():

                if pd.notna(row["Title"]):

                    title = str(row["Title"]).strip()

                    date_lookup[title] = parse_date(
                        row[date_column]
                    )

            filtered_results = []

            for result in domain_filtered_results:

                title = result["Original Title"]

                original_date = date_lookup.get(title)

                result_date = parse_date(
                    result["Result Published Date"]
                )

                # Remove ONLY results published earlier
                if (
                    original_date is not None
                    and result_date is not None
                    and result_date < original_date
                ):
                    continue

                # Retain same-day, later and undated
                filtered_results.append({
                    "Original Title": title,
                    "Original Published Date": (
                        original_date.isoformat()
                        if original_date else ""
                    ),
                    "Media Outlet": result["Media Outlet"],
                    "Result Title": result["Result Title"],
                    "Result Published Date": (
                        result_date.isoformat()
                        if result_date else ""
                    ),
                    "URL": result["URL"]
                })

            # ====================================
            # STEP 4: DISPLAY RESULTS
            # ====================================

            columns = [
                "Original Title",
                "Original Published Date",
                "Media Outlet",
                "Result Title",
                "Result Published Date",
                "URL"
            ]

            df_results = pd.DataFrame(
                filtered_results,
                columns=columns
            )

            st.subheader("Discovery Results")

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "Google Results",
                    len(all_results)
                )

            with col2:
                st.metric(
                    "After Domain Filter",
                    len(domain_filtered_results)
                )

            with col3:
                st.metric(
                    "Removed by Date",
                    len(domain_filtered_results)
                    - len(filtered_results)
                )

            with col4:
                st.metric(
                    "Final Results",
                    len(filtered_results)
                )

            st.dataframe(
                df_results,
                use_container_width=True
            )

            # ====================================
            # STEP 5: EXPORT CSV
            # ====================================

            csv_buffer = io.StringIO()

            df_results.to_csv(
                csv_buffer,
                index=False,
                encoding="utf-8-sig"
            )

            st.download_button(
                label="Download Media_Coverage_Report.csv",
                data=csv_buffer.getvalue(),
                file_name="Media_Coverage_Report.csv",
                mime="text/csv"
            )

            if df_results.empty:
                st.info(
                    "No media results found after filtering."
                )

elif not api_key and uploaded_file:

    st.info(
        "Please enter your SerpApi Key "
        "in the sidebar to begin."
    )
