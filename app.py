import streamlit as st
import pandas as pd
import pdfplumber

st.set_page_config(page_title="SE Ranking Baseline Comparison", layout="wide")
st.title("📊 SE Ranking Keyword & Baseline Comparison")

st.markdown("Upload two monthly SE Ranking PDF exports to compare **Keyword** vs **Baseline** rankings.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Month 1 PDF (e.g., April)", type=["pdf"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Month 2 PDF (e.g., May)", type=["pdf"], key="m2")

def parse_se_ranking_tables(pdf_file):
    """Extracts tables directly using pdfplumber's table engine to parse Keyword and Baseline."""
    extracted_rows = []
    current_engine = "Google Desktop"

    with pdfplumber.open(pdf_file) as pdf:
        # Loop starting from Page 3 (index 2)
        for page_idx in range(2, len(pdf.pages)):
            page = pdf.pages[page_idx]

            # Detect Search Engine heading from page text
            page_text = page.extract_text() or ""
            if "Google Mobile" in page_text:
                current_engine = "Google Mobile"
            elif "Google USA" in page_text or "Google" in page_text:
                if "Mobile" not in page_text:
                    current_engine = "Google Desktop"

            # Extract tables using pdfplumber's visual grid detection
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    # Clean up empty values and strip whitespace/newlines caused by line wraps
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                    
                    # Filter out empty rows or short artifacts
                    if len(clean_row) < 3 or not clean_row[0]:
                        continue

                    kw = clean_row[0]
                    baseline_val = clean_row[2]  # Column 0 = Keyword, Column 1 = Results, Column 2 = Baseline

                    # Filter out headers and metadata
                    if kw.lower() in ['keyword', 'results', 'baseline', ''] or 'brief rankings history' in kw.lower():
                        continue
                    if 'rankings overview' in kw.lower() or kw.startswith('General'):
                        continue

                    # Validate that baseline is a valid numeric rank
                    if baseline_val.isdigit():
                        extracted_rows.append({
                            'Engine': current_engine,
                            'Keyword': kw,
                            'Baseline': int(baseline_val)
                        })

    if not extracted_rows:
        return None

    df = pd.DataFrame(extracted_rows)
    # Deduplicate in case repeated rows exist across page breaks
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df

if file_m1 and file_m2:
    with st.spinner("Processing PDF tables..."):
        df_m1 = parse_se_ranking_tables(file_m1)
        df_m2 = parse_se_ranking_tables(file_m2)

    if df_m1 is not None and df_m2 is not None:
        # Search Engine / Device filter
        available_engines = list(set(df_m1['Engine'].unique()).union(set(df_m2['Engine'].unique())))
        selected_engine = st.selectbox("Select Engine / Device:", available_engines)

        # Filter subsets
        m1_sub = df_m1[df_m1['Engine'] == selected_engine][['Keyword', 'Baseline']].rename(columns={'Baseline': 'Prev_Baseline'})
        m2_sub = df_m2[df_m2['Engine'] == selected_engine][['Keyword', 'Baseline']].rename(columns={'Baseline': 'Curr_Baseline'})

        # Outer merge on Keyword
        merged = pd.merge(m1_sub, m2_sub, on='Keyword', how='outer')

        # Fill missing rankings with 100 (Unranked)
        merged['Prev_Baseline'] = merged['Prev_Baseline'].fillna(100).astype(int)
        merged['Curr_Baseline'] = merged['Curr_Baseline'].fillna(100).astype(int)

        # Rank movement calculation (Previous - Current)
        # Positive = Rank Improved (e.g., Prev 48 -> Curr 37 = +11)
        merged['Position Shift'] = merged['Prev_Baseline'] - merged['Curr_Baseline']

        def get_status(row):
            if row['Prev_Baseline'] == 100 and row['Curr_Baseline'] < 100:
                return "🆕 New Keyword"
            elif row['Prev_Baseline'] < 100 and row['Curr_Baseline'] == 100:
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
        m4.metric("New Keywords", len(merged[merged['Status'] == "🆕 New Keyword"]))

        # Status Filter & Dataframe Display
        status_filter = st.multiselect("Filter by Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)]

        st.dataframe(
            filtered_df.sort_values(by='Position Shift', ascending=False),
            use_container_width=True
        )
    else:
        st.error("Could not find table data in the uploaded PDFs. Please check that both files contain the Brief Rankings History table.")
