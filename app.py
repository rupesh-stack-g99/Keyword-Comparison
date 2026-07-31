import streamlit as st
import pandas as pd
import pdfplumber

st.set_page_config(page_title="SE Ranking PDF Comparison Tool", layout="wide")
st.title("📊 SE Ranking Brief History PDF Comparison")

st.markdown("Upload two monthly SE Ranking PDF reports (e.g., April vs. May) to compare position shifts.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Month 1 PDF (e.g., April)", type=["pdf"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Month 2 PDF (e.g., May)", type=["pdf"], key="m2")

def parse_se_ranking_pdf(pdf_file):
    """Robust parser for SE Ranking 'Brief Rankings History' tables."""
    extracted_rows = []
    current_engine = "Google Desktop"

    with pdfplumber.open(pdf_file) as pdf:
        # Start reading from page 3 (index 2) onwards
        for page_idx in range(2, len(pdf.pages)):
            page = pdf.pages[page_idx]
            
            # Extract plain text first to monitor Search Engine context
            text = page.extract_text() or ""
            lines = text.split("\n")

            # Extract full text lines to parse fallback rows
            for line in lines:
                line_clean = line.strip()

                # Track search engine switch
                if "Google Mobile" in line_clean:
                    current_engine = "Google Mobile"
                    continue
                elif "Google USA" in line_clean or "Google" in line_clean and "Austin" in line_clean:
                    if "Mobile" not in line_clean:
                        current_engine = "Google Desktop"
                    continue

                # Split on pipe '|' or multiple spaces
                parts = [p.strip() for p in line_clean.split('|') if p.strip()]
                
                # SE Ranking row standard structure: [Keyword, Results, Baseline/Rank]
                if len(parts) >= 3:
                    kw_candidate = parts[0]
                    rank_candidate = parts[-1]

                    # Verify last element is numeric rank
                    if rank_candidate.isdigit():
                        # Exclude headers / meta text
                        if kw_candidate.lower() not in ['keyword', 'results', 'baseline']:
                            extracted_rows.append({
                                'Engine': current_engine,
                                'Keyword': kw_candidate,
                                'Rank': int(rank_candidate)
                            })
                elif len(parts) == 1:
                    # Alternative split for non-pipe layouts (space separated numbers at the end)
                    tokens = line_clean.rsplit(maxsplit=2)
                    if len(tokens) == 3 and tokens[1].replace('K', '').replace('M', '').replace('.', '').isdigit() and tokens[2].isdigit():
                        extracted_rows.append({
                            'Engine': current_engine,
                            'Keyword': tokens[0].strip(),
                            'Rank': int(tokens[2])
                        })

    if not extracted_rows:
        return None

    df = pd.DataFrame(extracted_rows)
    # Deduplicate in case repeated rows exist across page headers
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df

if file_m1 and file_m2:
    with st.spinner("Extracting keyword ranking data..."):
        df_m1 = parse_se_ranking_pdf(file_m1)
        df_m2 = parse_se_ranking_pdf(file_m2)

    if df_m1 is not None and df_m2 is not None:
        # Select Search Engine View
        engine_options = list(set(df_m1['Engine'].unique()).union(set(df_m2['Engine'].unique())))
        selected_engine = st.selectbox("Select Device / Search Engine:", engine_options)

        # Filter by selected engine
        m1_sub = df_m1[df_m1['Engine'] == selected_engine][['Keyword', 'Rank']].rename(columns={'Rank': 'Prev_Rank'})
        m2_sub = df_m2[df_m2['Engine'] == selected_engine][['Keyword', 'Rank']].rename(columns={'Rank': 'Curr_Rank'})

        # Merge month 1 and month 2 on Keyword
        merged = pd.merge(m1_sub, m2_sub, on='Keyword', how='outer')

        # Treat missing keywords as unranked (>100)
        merged['Prev_Rank'] = merged['Prev_Rank'].fillna(100).astype(int)
        merged['Curr_Rank'] = merged['Curr_Rank'].fillna(100).astype(int)

        # Position Shift (Positive = Improvement)
        merged['Position Shift'] = merged['Prev_Rank'] - merged['Curr_Rank']

        def get_status(row):
            if row['Prev_Rank'] == 100 and row['Curr_Rank'] < 100:
                return "🆕 New Keyword"
            elif row['Prev_Rank'] < 100 and row['Curr_Rank'] == 100:
                return "❌ Dropped Out (>100)"
            elif row['Position Shift'] > 0:
                return "🟢 Improved"
            elif row['Position Shift'] < 0:
                return "🔴 Dropped"
            else:
                return "⚪ No Change"

        merged['Status'] = merged.apply(get_status, axis=1)

        # Overview Metrics
        st.subheader(f"Summary for {selected_engine}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Keywords", len(merged))
        m2.metric("Improved Positions", len(merged[merged['Position Shift'] > 0]))
        m3.metric("Dropped Positions", len(merged[merged['Position Shift'] < 0]))
        m4.metric("New Rankings", len(merged[merged['Status'] == "🆕 New Keyword"]))

        # Data Table & Filters
        status_filter = st.multiselect("Filter Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)]

        st.dataframe(
            filtered_df.sort_values(by='Position Shift', ascending=False),
            use_container_width=True
        )
    else:
        st.error("Could not parse keyword data from one or both files. Check that both PDFs follow the 'Brief Rankings History' format.")
