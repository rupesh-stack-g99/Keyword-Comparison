import streamlit as st
import pandas as pd

st.set_page_config(page_title="SE Ranking Comparison Tool", layout="wide")
st.title("📊 Keyword Ranking Month-over-Month Comparison")

st.markdown("Upload your monthly SE Ranking CSV or Excel exports below to compare position shifts.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Previous Month Export", type=["csv", "xlsx"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Current Month Export", type=["csv", "xlsx"], key="m2")

if file_m1 and file_m2:
    # Helper function to read file formats
    def load_data(file):
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        return pd.read_excel(file)

    df_m1 = load_data(file_m1)
    df_m2 = load_data(file_m2)

    # Note: Adjust 'Keyword' and 'Rank' column names if SE Ranking headers differ in your export
    kw_col = 'Keyword'
    rank_col = 'Rank'

    if kw_col in df_m1.columns and kw_col in df_m2.columns:
        # Keep necessary columns
        m1_subset = df_m1[[kw_col, rank_col]].rename(columns={rank_col: 'Prev_Rank'})
        m2_subset = df_m2[[kw_col, rank_col]].rename(columns={rank_col: 'Curr_Rank'})

        # Convert ranks to numeric, setting unranked/missing as NaN or 100
        m1_subset['Prev_Rank'] = pd.to_numeric(m1_subset['Prev_Rank'], errors='coerce').fillna(100)
        m2_subset['Curr_Rank'] = pd.to_numeric(m2_subset['Curr_Rank'], errors='coerce').fillna(100)

        # Merge datasets on Keyword
        merged = pd.merge(m1_subset, m2_subset, on=kw_col, how='outer')

        # Calculate Rank Change (Previous Rank - Current Rank)
        # Positive change = Position Improved (e.g., moved from rank 10 to 3 = +7)
        merged['Change'] = merged['Prev_Rank'] - merged['Curr_Rank']

        # Classify status
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

        # Overview Metrics
        st.subheader("Summary Overview")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Total Keywords", len(merged))
        m_col2.metric("Improved Ranks", len(merged[merged['Change'] > 0]))
        m_col3.metric("Dropped Ranks", len(merged[merged['Change'] < 0]))
        m_col4.metric("New Keywords", len(merged[merged['Status'] == "🆕 New Keyword"]))

        # Filter option
        status_filter = st.multiselect(
            "Filter by Status:",
            options=merged['Status'].unique(),
            default=merged['Status'].unique()
        )

        filtered_df = merged[merged['Status'].isin(status_filter)]

        st.subheader("Comparison Data")
        st.dataframe(
            filtered_df.sort_values(by='Change', ascending=False),
            use_container_width=True
        )
    else:
        st.error(f"Could not find required column '{kw_col}' in one or both files. Please verify column names.")
