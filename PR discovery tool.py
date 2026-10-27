import io

import pandas as pd
import streamlit as st
from serpapi import GoogleSearch


# --- UI Setup ---

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
Upload a CSV containing a **Title** column, enter your SerpApi key,
and search Google for coverage of each press release.
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

    if "Title" not in df_input.columns:
        st.error("CSV must contain a column named 'Title'.")

    else:
        st.success(
            f"CSV loaded successfully — {len(df_input)} rows found."
        )

        if st.button("Start Discovery Process"):
            titles = (
                df_input["Title"]
                .dropna()
                .astype(str)
                .str.strip()
            )
            titles = titles[titles != ""].drop_duplicates().tolist()

            if not titles:
                st.warning("No valid titles found.")
                st.stop()

            results_storage = []
            seen_results = set()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, title in enumerate(titles):
                status_text.text(
                    f"Searching ({i + 1}/{len(titles)}): "
                    f"{title[:50]}..."
                )

                # Exact-title search
                query = f'"{title}"'

                # Search up to two Google result pages
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

                        if response.get("error"):
                            st.warning(
                                f"Search failed for '{title}' "
                                f"(page {page + 1}): {response['error']}"
                            )
                            continue

                        organic_results = response.get(
                            "organic_results",
                            []
                        )

                        if not organic_results:
                            break

                        for result in organic_results:
                            link = (result.get("link") or "").strip()

                            if not link:
                                continue

                            # Exclude specified domains
                            link_lower = link.lower()
                            if any(
                                domain in link_lower
                                for domain in exclude_list
                            ):
                                continue

                            # Avoid duplicate URLs for the same title
                            result_key = (title.casefold(), link_lower)
                            if result_key in seen_results:
                                continue

                            seen_results.add(result_key)

                            results_storage.append({
                                "Original Title": title,
                                "Media Outlet": (
                                    result.get("source")
                                    or result.get("displayed_link")
                                    or ""
                                ),
                                "Result Title": result.get("title", ""),
                                "URL": link,
                            })

                    except Exception as e:
                        st.warning(
                            f"Search failed for '{title}' "
                            f"(page {page + 1}): {e}"
                        )

                progress_bar.progress((i + 1) / len(titles))

            status_text.empty()

            columns = [
                "Original Title",
                "Media Outlet",
                "Result Title",
                "URL",
            ]
            df_results = pd.DataFrame(
                results_storage,
                columns=columns
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
                    "No results were found based on the current "
                    "search and exclusion filters."
                )

elif uploaded_file and not api_key:
    st.info("Please enter your SerpApi Key in the sidebar to begin.")
