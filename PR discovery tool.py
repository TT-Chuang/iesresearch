import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import io

# --- UI Setup (English Interface) ---
st.set_page_config(page_title="PR Media Discovery Tool", layout="wide")

st.title("🔍 PR Media Discovery Tool")
st.markdown("""
This tool helps you find third-party media coverage by mimicking the **Newswise Search Formula**.
1. Enter your API Key.
2. Upload your CSV with a **'Title'** column.
3. Download the verified evidence list.
""")

# --- Sidebar: User Credentials ---
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Enter your SerpApi Key", type="password")
    exclude_domains = st.text_area("Domains to Exclude (one per line)", 
                                   value="newswise.com\nyoutube.com\nfacebook.com\nlinkedin.com\ntwitter.com")
    exclude_list = exclude_domains.split('\n')

# --- Main Logic ---
uploaded_file = st.file_uploader("Upload your Input_PR_Titles.csv", type=["csv"])

if uploaded_file and api_key:
    # Read CSV
    df_input = pd.read_csv(uploaded_file)
    # Normalize columns
    df_input.columns = [c.strip() for c in df_input.columns]

    if 'Title' not in df_input.columns:
        st.error("Error: CSV must contain a column named 'Title'")
    else:
        st.success("CSV Loaded Successfully!")
        
        if st.button("Start Discovery Process"):
            results_storage = []
            titles = df_input['Title'].dropna().tolist()
            
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, title in enumerate(titles):
                status_text.text(f"Searching ({i+1}/{len(titles)}): {title[:50]}...")
                
                # Newswise Formula: "Title "
                query = f'"{title.strip()} "'
                
                params = {
                    "engine": "google",
                    "q": query,
                    "hl": "en",
                    "filter": "0",  # Unlocks hidden results
                    "sort": "date",
                    "api_key": api_key
                }

                try:
                    search = GoogleSearch(params)
                    results = search.get_dict().get("organic_results", [])
                    
                    for res in results:
                        link = res.get("link", "")
                        if not any(domain.strip() in link for domain in exclude_list if domain.strip()):
                            results_storage.append({
                                "Original_Title": title,
                                "Media_Outlet": res.get("source"),
                                "Evidence_Link": link,
                                "Snippet": res.get("snippet", ""),
                                "Status": "Ready for Screenshot"
                            })
                except Exception as e:
                    st.warning(f"Search failed for {title}: {e}")
                
                progress_bar.progress((i + 1) / len(titles))

            # --- Results Display & Download ---
            if results_storage:
                df_results = pd.DataFrame(results_storage)
                st.subheader("Discovery Results")
                st.dataframe(df_results)

                # Convert to CSV for download
                csv_buffer = io.StringIO()
                df_results.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 Download Media_Coverage_Report.csv",
                    data=csv_buffer.getvalue(),
                    file_name="Media_Coverage_Report.csv",
                    mime="text/csv"
                )
            else:
                st.info("No third-party media found based on the filters.")

elif not api_key and uploaded_file:
    st.info("Please enter your SerpApi Key in the sidebar to begin.")
