import streamlit as st
import pandas as pd
import pdfplumber
import re

st.set_page_config(page_title="SE Ranking PDF Comparison Tool", layout="wide")
st.title("📊 SE Ranking Brief History PDF Comparison")

st.markdown("Upload two monthly SE Ranking PDF reports (e.g., April vs. May) to compare keyword positions.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Month 1 PDF (e.g., April)", type=["pdf"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Month 2 PDF (e.g., May)", type=["pdf"], key="m2")

def parse_se_ranking_pdf(pdf_file):
    """Parses SE Ranking 'Brief Rankings History' tables from Page 3 onwards."""
    extracted_data = []
    current_engine = "Google USA" # Default fallback
    
    with pdfplumber.open(pdf_file) as pdf:
        # Loop through pages starting from page 3 (index 2)
        for page_num in range(2, len(pdf.pages)):
            text_lines = pdf.pages[page_num].extract_text().split('\n')
            
            for line in text_lines:
                # Detect Search Engine Section (e.g., Google USA vs Google Mobile)
                if "Google" in line and "Austin" in line:
                    if "Mobile" in line:
                        current_engine = "Google Mobile"
                    else:
                        current_engine = "Google Desktop"
                    continue
                
                # Regex match for SE Ranking row pattern: [Keyword Name] | [Results] | [Rank]
                # Example line: "Body Contouring in Austin, TX | 150 | 48"
                match = re.search(r'^(.*?)\s*\|\s*[\d\.\,\w]+\s*\|\s*(\d+)$', line.strip())
                if match:
                    keyword = match.group(1).strip()
                    rank = int(match.group(2))
                    
                    # Ignore header/footer artifacts
                    if keyword.lower() not in ['keyword', 'results', 'baseline', 'brief rankings history']:
                        extracted_data.append({
                            'Engine': current_engine,
                            'Keyword': keyword,
                            'Rank': rank
                        })

    if not extracted_data:
        return None
        
    df = pd.DataFrame(extracted_data)
    # Deduplicate in case a keyword is listed twice under same engine
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df

if file_m1 and file_m2:
    with st.spinner("Parsing PDFs from Page 3..."):
        df_m1 = parse_se_ranking_pdf(file_m1)
        df_m2 = parse_se_ranking_pdf(file_m2)

    if df_m1 is not None and df_m2 is not None:
        # Select Search Engine View
        engine_options = list(set(df_m1['Engine'].unique()).union(set(df_m2['Engine'].unique())))
        selected_engine = st.selectbox("Select Device / Search Engine:", engine_options)

        # Filter by selected search engine
        m1_sub = df_m1[df_m1['Engine'] == selected_engine][['Keyword', 'Rank']].rename(columns={'Rank': 'Prev_Rank'})
        m2_sub = df_m2[df_m2['Engine'] == selected_engine][['Keyword', 'Rank']].rename(columns={'Rank': 'Curr_Rank'})

        # Merge datasets on Keyword
        merged = pd.merge(m1_sub, m2_sub, on='Keyword', how='outer')

        # Fill missing rankings (if keyword dropped off top 100)
        merged['Prev_Rank'] = merged['Prev_Rank'].fillna(100).astype(int)
        merged['Curr_Rank'] = merged['Curr_Rank'].fillna(100).astype(int)

        # Rank movement (Positive = rank improved)
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

        # Summary Statistics
        st.subheader(f"Summary for {selected_engine}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Keywords", len(merged))
        m2.metric("Improved Positions", len(merged[merged['Position Shift'] > 0]))
        m3.metric("Dropped Positions", len(merged[merged['Position Shift'] < 0]))
        m4.metric("New Rankings", len(merged[merged['Status'] == "🆕 New Keyword"]))

        # Filtering & Output
        status_filter = st.multiselect("Filter by Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)]

        st.dataframe(
            filtered_df.sort_values(by='Position Shift', ascending=False),
            use_container_width=True
        )
    else:
        st.error("Could not parse keyword data from the uploaded PDFs. Please make sure the PDF has the 'Brief Rankings History' format on page 3 onwards.")
