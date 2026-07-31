import streamlit as st
import pandas as pd
import pdfplumber

st.set_page_config(page_title="SE Ranking PDF Comparison Tool", layout="wide")
st.title("📄 SE Ranking PDF Keyword Comparison")

st.markdown("Upload your monthly SE Ranking **PDF exports** below to compare position shifts.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Previous Month PDF", type=["pdf"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Current Month PDF", type=["pdf"], key="m2")

def extract_table_from_pdf(pdf_file):
    """Extracts tables across all pages in a PDF and merges them into one DataFrame."""
    all_rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Filter out empty rows or repeated headers
                    if row and any(row):
                        all_rows.append(row)
    
    if not all_rows:
        return None

    # First row is treated as header
    headers = [str(col).strip() if col else f"col_{i}" for i, col in enumerate(all_rows[0])]
    df = pd.DataFrame(all_rows[1:], columns=headers)
    return df

if file_m1 and file_m2:
    with st.spinner("Extracting data from PDF files..."):
        df_m1 = extract_table_from_pdf(file_m1)
        df_m2 = extract_table_from_pdf(file_m2)

    if df_m1 is not None and df_m2 is not None:
        st.write("### Detected Columns")
        st.write("Previous Month Columns:", list(df_m1.columns))
        st.write("Current Month Columns:", list(df_m2.columns))

        # Column selectors in case column names differ slightly in SE Ranking exports
        c1, c2 = st.columns(2)
        kw_col = c1.selectbox("Select Keyword Column", df_m1.columns, index=0)
        
        # Default to finding 'Rank' or 'Position' column
        default_rank_idx = 1
        for idx, col in enumerate(df_m1.columns):
            if "rank" in col.lower() or "pos" in col.lower():
                default_rank_idx = idx
                break
                
        rank_col = c2.selectbox("Select Rank Column", df_m1.columns, index=default_rank_idx)

        # Prepare subsets
        m1_sub = df_m1[[kw_col, rank_col]].copy().rename(columns={rank_col: 'Prev_Rank'})
        m2_sub = df_m2[[kw_col, rank_col]].copy().rename(columns={rank_col: 'Curr_Rank'})

        # Clean numeric rank columns
        m1_sub['Prev_Rank'] = pd.to_numeric(m1_sub['Prev_Rank'].astype(str).str.extract(r'(\d+)')[0], errors='coerce').fillna(100)
        m2_sub['Curr_Rank'] = pd.to_numeric(m2_sub['Curr_Rank'].astype(str).str.extract(r'(\d+)')[0], errors='coerce').fillna(100)

        # Merge datasets
        merged = pd.merge(m1_sub, m2_sub, on=kw_col, how='outer')

        # Calculate Rank Position Change
        merged['Change'] = merged['Prev_Rank'] - merged['Curr_Rank']

        def get_status(row):
            if row['Prev_Rank'] == 100 and row['Curr_Rank'] < 100:
                return "🆕 New Keyword"
            elif row['Prev_Rank'] < 100 and row['Curr_Rank'] == 100:
                return "❌ Lost Keyword"
            elif row['Change'] > 0:
                return "🟢 Improved"
            elif row['Change'] < 0:
                return "🔴 Dropped"
            else:
                return "⚪ No Change"

        merged['Status'] = merged.apply(get_status, axis=1)

        # Summary Metrics
        st.subheader("Comparison Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Keywords", len(merged))
        m2.metric("Improved Ranks", len(merged[merged['Change'] > 0]))
        m3.metric("Dropped Ranks", len(merged[merged['Change'] < 0]))
        m4.metric("New Keywords", len(merged[merged['Status'] == "🆕 New Keyword"]))

        # Filter & Data Table
        status_filter = st.multiselect("Filter Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)]

        st.dataframe(filtered_df.sort_values(by='Change', ascending=False), use_container_width=True)
    else:
        st.error("Could not extract tables from one or both PDF files. Ensure the PDF contains recognizable tables.")
