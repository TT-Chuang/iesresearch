import io
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from serpapi import GoogleSearch


# --- Helpers ---

def normalize_domain(value):
    """Normalize a domain or URL to a lowercase hostname."""
    value = str(value).strip().lower()

    if not value:
        return ""

    # Allow users to enter either a domain or a full URL.
    if "://" not in value:
        value = f"//{value}"

    host = urlparse(value).hostname or ""
    return host.lower().removeprefix("www.")


def domain_matches(url, domains):
    """Return True if the URL host matches a domain or its subdomain."""
    host = normalize_domain(url)

    if not host:
        return False

    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in domains
    )


# --- UI Setup ---

st.set_page_config(
    page_title="PR Media Discovery Tool",
    layout="wide"
)

st.title("🔍 PR Media Discovery Tool")

st.markdown("""
Search Google News for coverage of each press release title.

Results are limited to two pages per title and included only when the
result comes from an approved media outlet domain.
""")


# --- Sidebar: Settings ---

with st.sidebar:
    st.header("Settings")

    api_key = st.text_input(
        "Enter your SerpApi Key",
        type="password"
    )

    approved_domains_text = st.text_area(
        "Approved media outlet domains (one per line)",
        help=(
            "Only results from these domains will be included. "
            "Enter domains such as example.com."
        )
    )

    approved_domains = {
        normalize_domain(line)
        for line in approved_domains_text.splitlines()
        if normalize_domain(line)
    }

    exclude_domains_text = st.text_area(
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

    exclude_domains = {
        normalize_domain(line)
        for line in exclude_domains_text.splitlines()
        if normalize_domain(line)
    }

    st.caption("The search is limited to two Google News pages per title.")


# --- File Upload ---

uploaded_file = st.file_uploader(
    "Upload your Input_PR_Titles.csv",
    type=["csv"]
)


# --- Main Logic ---

if uploaded_file:
    try:
        df_input = pd.read_csv(uploaded_file)
        df_input.columns = [str(column).strip() for column in df_input.columns]

    except Exception as e:
        st.error(f"Unable to read CSV: {e}")
        st.stop()

    if "Title" not in df_input.columns:
        st.error("The CSV must contain a column named 'Title'.")

    else:
        st.success(
            f"CSV loaded successfully — {len(df_input)} rows found."
        )

        if not api_key:
            st.info("Enter your SerpApi Key in the sidebar to begin.")

        if not approved_domains:
            st.info(
                "Add at least one approved media outlet domain "
                "in the sidebar to filter the results."
            )

        start_search = st.button(
            "Start Discovery Process",
            disabled=not api_key or not approved_domains
        )

        if start_search:
            # Clean titles: remove blanks and duplicate titles.
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

            # Search each title on up to two Google News pages.
            for title_index, title in enumerate(titles):
                status_text.text(
                    f"Searching ({title_index + 1}/{len(titles)}): "
                    f"{title[:80]}"
                )

                query = f'"{title}"'

                for page in range(2):
                    params = {
                        "engine": "google",
                        "tbm": "nws",
                        "q": query,
                        "hl": "en",
                        "start": page * 10,
                        "api_key": api_key,
                    }

                    try:
                        response = GoogleSearch(params).get_dict()

                        if response.get("error"):
                            st.warning(
                                f"Search failed for '{title}' "
                                f"(page {page + 1}): "
                                f"{response['error']}"
                            )
                            continue

                        news_results = response.get("news_results", [])

                        if not news_results:
                            break

                        for result in news_results:
                            link = (result.get("link") or "").strip()
                            outlet = (result.get("source") or "").strip()
                            result_title = (
                                result.get("title") or ""
                            ).strip()

                            # Require a URL, publisher name, and approved domain.
                            if not link or not outlet:
                                continue

                            if not domain_matches(link, approved_domains):
                                continue

                            if domain_matches(link, exclude_domains):
                                continue

                            # Avoid duplicate URLs for the same PR title.
                            result_key = (title.casefold(), link)

                            if result_key in seen_results:
                                continue

                            seen_results.add(result_key)

                            results_storage.append({
                                "Original Title": title,
                                "Media Outlet": outlet,
                                "Result Title": result_title,
                                "URL": link,
                            })

                    except Exception as e:
                        st.warning(
                            f"Search failed for '{title}' "
                            f"(page {page + 1}): {e}"
                        )

                progress_bar.progress(
                    (title_index + 1) / len(titles)
                )

            status_text.empty()

            # Keep the requested column order, including for an empty result set.
            columns = [
                "Original Title",
                "Media Outlet",
                "Result Title",
                "URL",
            ]
            df_results = pd.DataFrame(results_storage, columns=columns)

            st.subheader("Discovery Results")
            st.write(
                f"Found **{len(df_results)} results** "
                f"across **{len(titles)} unique PR titles**."
            )

            if not df_results.empty:
                st.dataframe(
                    df_results,
                    use_container_width=True
                )

                csv_buffer = io.StringIO()
                df_results.to_csv(
                    csv_buffer,
                    index=False
                )

                st.download_button(
                    label="📥 Download Media_Coverage_Report.csv",
                    data=csv_buffer.getvalue(),
                    file_name="Media_Coverage_Report.csv",
                    mime="text/csv"
                )
            else:
                st.info(
                    "No results matched the approved media outlet domains "
                    "and exclusion filters."
                )
