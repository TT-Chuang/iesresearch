import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import io

# --- UI Setup ---
st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
This tool searches Google for third-party media coverage based on the exact title of each press release.

### Search Logic
1. Search the exact PR title on Google.
2. Prioritize Google's relevance ranking.
3. Search multiple pages of Google results.
4. Remove excluded domains.
5. Remove duplicate URLs.
6. Export the remaining results for review.
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
        for domain in exclude_domains.split("\n")
        if domain.strip()
    ]

    pages_to_search = st.number_input(
        "Google pages to search per title",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
        help="3 pages = approximately 30 Google results per title."
    )


# --- File Upload ---
uploaded_file = st.file_uploader(
    "Upload your Input_PR_Titles.csv",
    type=["csv"]
)


# --- Main Logic ---
if uploaded_file and api_key:

    try:
        df_input = pd.read_csv(uploaded_file)

        # Normalize column names
        df_input.columns = [
            str(c).strip()
            for c in df_input.columns
        ]

    except Exception as e:
        st.error(f"Unable to read CSV: {e}")
        st.stop()


    if "Title" not in df_input.columns:

        st.error(
            "Error: CSV must contain a column named 'Title'."
        )

    else:

        st.success(
            f"CSV loaded successfully — {len(df_input)} rows found."
        )

        if st.button("Start Discovery Process"):

            results_storage = []

            # Clean title list
            titles = (
                df_input["Title"]
                .dropna()
                .astype(str)
                .str.strip()
            )

            # Remove blank titles
            titles = titles[titles != ""]

            # Remove duplicated titles
            titles = titles.drop_duplicates().tolist()

            if len(titles) == 0:
                st.warning("No valid titles found.")
                st.stop()

            progress_bar = st.progress(0)

            status_text = st.empty()

            # Used for deduplication across search pages
            seen_results = set()


            # ---------------------------------
            # SEARCH EACH PRESS RELEASE TITLE
            # ---------------------------------

            for i, title in enumerate(titles):

                status_text.text(
                    f"Searching ({i + 1}/{len(titles)}): "
                    f"{title[:80]}"
                )

                # Exact phrase search
                query = f'"{title}"'


                # Search multiple Google result pages
                for page in range(int(pages_to_search)):

                    start_position = page * 10

                    params = {
                        "engine": "google",
                        "q": query,
                        "hl": "en",

                        # Do not force date sorting.
                        # Let Google rank by relevance.
                        "filter": "0",

                        "num": 10,
                        "start": start_position,

                        "api_key": api_key
                    }


                    try:

                        search = GoogleSearch(params)

                        response = search.get_dict()

                        organic_results = response.get(
                            "organic_results",
                            []
                        )


                        # If Google returns no more results,
                        # stop searching additional pages.
                        if not organic_results:
                            break


                        for result in organic_results:

                            link = result.get(
                                "link",
                                ""
                            ).strip()

                            if not link:
                                continue


                            # -----------------------------
                            # DOMAIN EXCLUSION
                            # -----------------------------

                            link_lower = link.lower()

                            excluded = any(
                                domain in link_lower
                                for domain in exclude_list
                            )

                            if excluded:
                                continue


                            # -----------------------------
                            # DEDUPLICATION
                            # -----------------------------

                            # Keep duplicate URLs from
                            # appearing more than once
                            # for the same PR title.
                            result_key = (
                                title.lower(),
                                link_lower
                            )

                            if result_key in seen_results:
                                continue

                            seen_results.add(result_key)


                            # -----------------------------
                            # SAVE RESULT
                            # -----------------------------

                            results_storage.append({
                                "Original_Title": title,

                                "Media_Outlet": (
                                    result.get("source")
                                    or result.get("displayed_link")
                                    or ""
                                ),

                                "Search_Result_Title": (
                                    result.get("title", "")
                                ),

                                "Evidence_Link": link,

                                "Snippet": (
                                    result.get("snippet", "")
                                ),

                                "Google_Position": (
                                    result.get("position", "")
                                ),

                                "Google_Page": page + 1
                            })


                    except Exception as e:

                        st.warning(
                            f"Search failed for '{title}' "
                            f"(page {page + 1}): {e}"
                        )


                # Update progress
                progress_bar.progress(
                    (i + 1) / len(titles)
                )


            # ---------------------------------
            # RESULTS
            # ---------------------------------

            status_text.empty()

            if results_storage:

                df_results = pd.DataFrame(
                    results_storage
                )

                st.subheader("Discovery Results")

                st.write(
                    f"Found **{len(df_results)} results** "
                    f"across **{len(titles)} PR titles**."
                )

                st.dataframe(
                    df_results,
                    use_container_width=True
                )


                # ---------------------------------
                # CSV DOWNLOAD
                # ---------------------------------

                csv_buffer = io.StringIO()

                df_results.to_csv(
                    csv_buffer,
                    index=False,
                    encoding="utf-8-sig"
                )

                st.download_button(
                    label="📥 Download Media_Coverage_Report.csv",

                    data=csv_buffer.getvalue(),

                    file_name=(
                        "Media_Coverage_Report.csv"
                    ),

                    mime="text/csv"
                )


            else:

                st.info(
                    "No third-party media results were found "
                    "based on the current search and exclusion filters."
                )


elif uploaded_file and not api_key:

    st.info(
        "Please enter your SerpApi Key "
        "in the sidebar to begin."
    )
