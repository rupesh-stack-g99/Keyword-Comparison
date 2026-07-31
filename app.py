import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="SE Ranking Comparison Tool", layout="wide")
st.title("📊 SE Ranking Keyword & Ranking Comparison")

st.markdown("Upload two monthly SE Ranking PDF exports to compare **Keyword** vs **Ranking** data.")

col1, col2 = st.columns(2)

with col1:
    file_m1 = st.file_uploader("Upload Month 1 PDF (e.g., April)", type=["pdf"], key="m1")
with col2:
    file_m2 = st.file_uploader("Upload Month 2 PDF (e.g., May)", type=["pdf"], key="m2")


def extract_month_from_pdf(pdf_file):
    """Attempts to extract the report month or date range from the first page of the PDF."""
    try:
        pdf_file.seek(0)
        with pdfplumber.open(pdf_file) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            months = re.findall(
                r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)',
                first_page_text,
                re.IGNORECASE
            )
            if months:
                return months[-1].capitalize()
    except Exception:
        pass
    return None


def parse_se_ranking_tables(pdf_file):
    """Extracts tables directly using pdfplumber's table engine to parse Keyword and Baseline (Ranking)."""
    pdf_file.seek(0)
    extracted_rows = []
    current_engine = "Google Desktop"

    with pdfplumber.open(pdf_file) as pdf:
        # Loop starting from Page 3 (index 2)
        for page_idx in range(2, len(pdf.pages)):
            page = pdf.pages[page_idx]

            page_text = page.extract_text() or ""
            if "Google Mobile" in page_text:
                current_engine = "Google Mobile"
            elif "Google USA" in page_text or "Google" in page_text:
                if "Mobile" not in page_text:
                    current_engine = "Google Desktop"

            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]

                    if len(clean_row) < 3 or not clean_row[0]:
                        continue

                    kw = clean_row[0]
                    baseline_val = clean_row[2]  # Column 0 = Keyword, Column 1 = Results, Column 2 = Baseline (Ranking)

                    # Filter out headers and metadata
                    if kw.lower() in ['keyword', 'results', 'baseline', ''] or 'brief rankings history' in kw.lower():
                        continue
                    if 'rankings overview' in kw.lower() or kw.startswith('General'):
                        continue

                    if baseline_val.isdigit():
                        extracted_rows.append({
                            'Engine': current_engine,
                            'Keyword': kw,
                            'Ranking': int(baseline_val)
                        })

    if not extracted_rows:
        return None

    df = pd.DataFrame(extracted_rows)
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df


def generate_pdf_report(dataframe, engine_name, label_m1, label_m2):
    """Generates a downloadable PDF document with custom dynamic month column headers."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []

    styles = getSampleStyleSheet()
    title_style = styles['Heading1']

    # Custom Subtitle Style to avoid KeyError
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=12
    )

    story.append(Paragraph(f"SE Ranking Comparison Report - {engine_name}", title_style))
    story.append(Paragraph(f"Period: {label_m1} vs {label_m2}", subtitle_style))
    story.append(Spacer(1, 12))

    # Dynamic Column Headers matching custom month labels
    m1_header = f"{label_m1} Rank" if "Rank" not in label_m1 else label_m1
    m2_header = f"{label_m2} Rank" if "Rank" not in label_m2 else label_m2

    table_data = [["Keyword", m1_header, m2_header, "Shift", "Status"]]
    for _, row in dataframe.iterrows():
        table_data.append([
            str(row['Keyword'])[:40],  # Truncate long keywords for clean layout
            str(row['Prev_Ranking']),
            str(row['Curr_Ranking']),
            f"{'+' if row['Position Shift'] > 0 else ''}{row['Position Shift']}",
            str(row['Status']).replace("🆕 ", "").replace("❌ ", "").replace("🟢 ", "").replace("🔴 ", "").replace("⚪ ", "")
        ])

    pdf_table = Table(table_data, colWidths=[240, 70, 70, 50, 100])
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
    ]))

    story.append(pdf_table)
    doc.build(story)
    buffer.seek(0)
    return buffer


if file_m1 and file_m2:
    # Auto-detect months or fall back to Month 1 / Month 2
    detected_m1 = extract_month_from_pdf(file_m1) or "Month 1"
    detected_m2 = extract_month_from_pdf(file_m2) or "Month 2"

    st.sidebar.subheader("🗓️ Report Labels Settings")
    label_m1 = st.sidebar.text_input("Previous Month Label:", value=f"{detected_m1} Ranking")
    label_m2 = st.sidebar.text_input("Current Month Label:", value=f"{detected_m2} Ranking")

    with st.spinner("Processing PDF tables..."):
        df_m1 = parse_se_ranking_tables(file_m1)
        df_m2 = parse_se_ranking_tables(file_m2)

    if df_m1 is not None and df_m2 is not None:
        available_engines = list(set(df_m1['Engine'].unique()).union(set(df_m2['Engine'].unique())))
        selected_engine = st.selectbox("Select Engine / Device:", available_engines)

        # Dynamic Subsets
        m1_sub = df_m1[df_m1['Engine'] == selected_engine][['Keyword', 'Ranking']].rename(columns={'Ranking': 'Prev_Ranking'})
        m2_sub = df_m2[df_m2['Engine'] == selected_engine][['Keyword', 'Ranking']].rename(columns={'Ranking': 'Curr_Ranking'})

        # Outer Merge
        merged = pd.merge(m1_sub, m2_sub, on='Keyword', how='outer')

        merged['Prev_Ranking'] = merged['Prev_Ranking'].fillna(100).astype(int)
        merged['Curr_Ranking'] = merged['Curr_Ranking'].fillna(100).astype(int)

        # Position Shift Calculation
        merged['Position Shift'] = merged['Prev_Ranking'] - merged['Curr_Ranking']

        def get_status(row):
            if row['Prev_Ranking'] == 100 and row['Curr_Ranking'] < 100:
                return "🆕 New Keyword"
            elif row['Prev_Ranking'] < 100 and row['Curr_Ranking'] == 100:
                return "❌ Dropped Out (>100)"
            elif row['Position Shift'] > 0:
                return "🟢 Improved"
            elif row['Position Shift'] < 0:
                return "🔴 Dropped"
            else:
                return "⚪ No Change"

        merged['Status'] = merged.apply(get_status, axis=1)

        # SEO Ranking Metrics
        curr_ranks = merged['Curr_Ranking']
        top_1_3 = len(merged[(curr_ranks >= 1) & (curr_ranks <= 3)])
        top_4_10 = len(merged[(curr_ranks >= 4) & (curr_ranks <= 10)])
        top_11_30 = len(merged[(curr_ranks >= 11) & (curr_ranks <= 30)])
        out_serp = len(merged[curr_ranks >= 100])

        ranked_keywords = merged[curr_ranks < 100]
        avg_pos = round(ranked_keywords['Curr_Ranking'].mean(), 1) if not ranked_keywords.empty else "N/A"

        st.subheader(f"SEO Performance Overview ({selected_engine})")

        # Metric Overview Cards
        r1_col1, r1_col2, r1_col3, r1_col4, r1_col5, r1_col6 = st.columns(6)
        r1_col1.metric("Total Keywords", len(merged))
        r1_col2.metric("Top 1-3", top_1_3)
        r1_col3.metric("Top 4-10", top_4_10)
        r1_col4.metric("Top 11-30", top_11_30)
        r1_col5.metric("Out of SERP", out_serp)
        r1_col6.metric("Avg. Position", avg_pos)

        r2_col1, r2_col2, r2_col3, r2_col4 = st.columns(4)
        r2_col1.metric("Improved Positions", len(merged[merged['Position Shift'] > 0]))
        r2_col2.metric("Dropped Positions", len(merged[merged['Position Shift'] < 0]))
        r2_col3.metric("New Keywords", len(merged[merged['Status'] == "🆕 New Keyword"]))
        r2_col4.metric("Dropped Out (>100)", out_serp)

        st.markdown("---")

        # Filters & Sorting
        status_filter = st.multiselect("Filter by Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)].sort_values(by='Position Shift', ascending=False)

        # Rename Dataframe Display Headers to match custom month labels
        display_df = filtered_df.rename(columns={
            'Prev_Ranking': label_m1,
            'Curr_Ranking': label_m2
        })

        # Fix Index to start from 1 instead of 0
        display_df.index = range(1, len(display_df) + 1)

        # Header with PDF Download Button
        head_col1, head_col2 = st.columns([4, 1])
        head_col1.subheader("Keyword Comparison Data")

        pdf_bytes = generate_pdf_report(filtered_df, selected_engine, label_m1, label_m2)
        head_col2.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"SE_Ranking_Comparison_{selected_engine}.pdf",
            mime="application/pdf"
        )

        st.dataframe(display_df, use_container_width=True)
    else:
        st.error("Could not find table data in the uploaded PDFs. Please check that both files contain the Brief Rankings History table.")
