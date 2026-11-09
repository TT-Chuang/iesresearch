
# --- Main Logic ---

uploaded_file = st.file_uploader(
    "Upload Input_PR_Titles.csv",
    type=["csv"]
)

if uploaded_file and api_key:

    df_input = pd.read_csv(uploaded_file)
    df_input.columns = [c.strip() for c in df_input.columns]

    date_column = next(
        (
            c for c in df_input.columns
            if c.lower() in ["published date", "date"]
        ),
        None
    )

    if "Title" not in df_input.columns:
        st.error("CSV must contain 'Title'.")

    elif date_column is None:
        st.error("CSV must contain 'Published Date' or 'Date'.")

    elif st.button("Start Discovery Process"):

        # ============================================
        # STEP 1: SEARCH AND COLLECT
        # Publication dates are NOT used here.
        # ============================================

        all_results = []

        titles = df_input["Title"].dropna().tolist()

        progress = st.progress(0)

        for i, title in enumerate(titles):

            title = str(title).strip()

            # Original Code 1 search formula
            query = f'"{title} "'

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

                    # Original Code 1 domain filtering
                    if any(
                        domain.strip() in link
                        for domain in exclude_list
                        if domain.strip()
                    ):
                        continue

                    # Collect first, WITHOUT date filtering
                    all_results.append({
                        "Original Title": title,
                        "Media Outlet": res.get("source", ""),
                        "Result Title": res.get("title", ""),
                        "Result Published Date": res.get("date"),
                        "URL": link
                    })

            except Exception as e:
                st.warning(f"Search failed for {title}: {e}")

            progress.progress((i + 1) / len(titles))

        # ============================================
        # STEP 2: FILTER AFTER COLLECTION
        # Publication dates are used ONLY here.
        # ============================================

        filtered_results = []

        # Match each result to its original PR date
        date_lookup = {}

        for _, row in df_input.iterrows():
            if pd.notna(row["Title"]):
                title = str(row["Title"]).strip()
                date_lookup[title] = parse_date(row[date_column])

        for result in all_results:

            title = result["Original Title"]

            original_date = date_lookup.get(title)

            result_date = parse_date(
                result["Result Published Date"]
            )

            # Remove ONLY confirmed earlier results
            if (
                original_date is not None
                and result_date is not None
                and result_date < original_date
            ):
                continue

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

        # ============================================
        # STEP 3: DISPLAY AND EXPORT
        # ============================================

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

        st.write(
            f"Collected: {len(all_results)} | "
            f"After date filter: {len(df_results)} | "
            f"Removed: {len(all_results) - len(df_results)}"
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
            "Download Media_Coverage_Report.csv",
            data=csv_buffer.getvalue(),
            file_name="Media_Coverage_Report.csv",
            mime="text/csv"
        )
