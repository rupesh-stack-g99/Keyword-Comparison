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


def clean_rank_value(val_str):
    """Cleans raw PDF text into a valid rank integer (1-100). Returns 100 if unranked/out of SERP."""
    if not val_str:
        return 100
    
    # Strip whitespace and common noise symbols
    val = re.sub(r'[^\d\->]', '', str(val_str)).strip()
    
    if not val or val == '-' or '>' in val:
        return 100
    
    if val.isdigit():
        num = int(val)
        # SE Ranking positions only go up to 100 on SERP. Values larger than 100 are total results or search volume.
        if 1 <= num <= 100:
            return num
        else:
            return 100
            
    return 100


def parse_se_ranking_tables(pdf_file):
    """Extracts tables across all pages using pdfplumber with strict column position targeted extraction."""
    pdf_file.seek(0)
    extracted_rows = []
    current_engine = "Google Desktop"

    with pdfplumber.open(pdf_file) as pdf:
        for page_idx in range(len(pdf.pages)):
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

                    # Ignore headers and summary blocks
                    if kw.lower() in ['keyword', 'results', 'baseline', 'ranking', ''] or 'brief rankings history' in kw.lower():
                        continue
                    if 'rankings overview' in kw.lower() or kw.startswith('General'):
                        continue

                    # SE Ranking exports usually have Rank in column index 2 or 3.
                    # We evaluate potential columns to extract genuine SERP positions (1-100).
                    rank_val = 100
                    
                    # Try candidate columns sequentially (Index 2, then 3, then 1)
                    for col_idx in [2, 3, 1]:
                        if col_idx < len(clean_row):
                            potential_val = clean_row[col_idx]
                            parsed_rank = clean_rank_value(potential_val)
                            # If a valid SERP position (1-100) is found, use it
                            if parsed_rank < 100 or potential_val in ['100', '>100', '-']:
                                rank_val = parsed_rank
                                break

                    extracted_rows.append({
                        'Engine': current_engine,
                        'Keyword': kw,
                        'Ranking': int(rank_val)
                    })

    if not extracted_rows:
        return None

    df = pd.DataFrame(extracted_rows)
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df


def generate_pdf_report(dataframe, engine_name, label_m1, label_m2):
    """Generates a downloadable PDF document with SEO Metrics Overview and dynamic headers."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )
    story = []

    styles = getSampleStyleSheet()
    title_style = styles['Heading1']

    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=10
    )

    cell_style = ParagraphStyle('TableCell', parent=styles['Normal'], fontSize=8, leading=10)
    metric_label_style = ParagraphStyle('MetricLabel', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#9ca3af'), alignment=1)
    metric_val_style = ParagraphStyle('MetricVal', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)

    # Title Section
    story.append(Paragraph(f"SE Ranking Comparison Report - {engine_name}", title_style))
    story.append(Paragraph(f"Period: {label_m1} vs {label_m2}", subtitle_style))
    story.append(Spacer(1, 8))

    # SEO Performance Overview Calculations
    curr_ranks = dataframe['Curr_Ranking']
    total_kw = len(dataframe)
    top_1_3 = len(dataframe[(curr_ranks >= 1) & (curr_ranks <= 3)])
    top_4_10 = len(dataframe[(curr_ranks >= 4) & (curr_ranks <= 10)])
    top_11_30 = len(dataframe[(curr_ranks >= 11) & (curr_ranks <= 30)])
    out_serp = len(dataframe[curr_ranks >= 100])
    
    ranked_kw = dataframe[curr_ranks < 100]
    avg_pos = round(ranked_kw['Curr_Ranking'].mean(), 1) if not ranked_kw.empty else "N/A"

    improved = len(dataframe[dataframe['Position Shift'] > 0])
    dropped = len(dataframe[dataframe['Position Shift'] < 0])
    new_kw = len(dataframe[dataframe['Status'].str.contains("New Keyword", na=False)])
    dropped_out = out_serp

    # Metrics Summary Table Layout
    metrics_data = [
        [
            Paragraph("Total Keywords", metric_label_style),
            Paragraph("Top 1-3", metric_label_style),
            Paragraph("Top 4-10", metric_label_style),
            Paragraph("Top 11-30", metric_label_style),
            Paragraph("Out of SERP", metric_label_style),
            Paragraph("Avg. Position", metric_label_style)
        ],
        [
            Paragraph(str(total_kw), metric_val_style),
            Paragraph(str(top_1_3), metric_val_style),
            Paragraph(str(top_4_10), metric_val_style),
            Paragraph(str(top_11_30), metric_val_style),
            Paragraph(str(out_serp), metric_val_style),
            Paragraph(str(avg_pos), metric_val_style)
        ],
        [
            Paragraph("Improved Positions", metric_label_style),
            Paragraph("Dropped Positions", metric_label_style),
            Paragraph("New Keywords", metric_label_style),
            Paragraph("Dropped Out (>100)", metric_label_style),
            Paragraph("", metric_label_style),
            Paragraph("", metric_label_style)
        ],
        [
            Paragraph(str(improved), metric_val_style),
            Paragraph(str(dropped), metric_val_style),
            Paragraph(str(new_kw), metric_val_style),
            Paragraph(str(dropped_out), metric_val_style),
            Paragraph("", metric_label_style),
            Paragraph("", metric_label_style)
        ]
    ]

    metrics_table = Table(metrics_data, colWidths=[95, 95, 95, 95, 95, 95])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#111827')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1f2937')),
    ]))

    story.append(metrics_table)
    story.append(Spacer(1, 14))

    # Keyword Data Table
    m1_header = f"{label_m1} Rank" if "Rank" not in label_m1 else label_m1
    m2_header = f"{label_m2} Rank" if "Rank" not in label_m2 else label_m2

    table_data = [[
        Paragraph("<b>Keyword</b>", cell_style),
        Paragraph(f"<b>{m1_header}</b>", cell_style),
        Paragraph(f"<b>{m2_header}</b>", cell_style),
        Paragraph("<b>Shift</b>", cell_style),
        Paragraph("<b>Status</b>", cell_style)
    ]]

    for _, row in dataframe.iterrows():
        clean_status = str(row['Status']).replace("🆕 ", "").replace("❌ ", "").replace("🟢 ", "").replace("🔴 ", "").replace("⚪ ", "")
        shift_str = f"+{row['Position Shift']}" if row['Position Shift'] > 0 else str(row['Position Shift'])
        
        table_data.append([
            Paragraph(str(row['Keyword']), cell_style),
            Paragraph(str(row['Prev_Ranking']), cell_style),
            Paragraph(str(row['Curr_Ranking']), cell_style),
            Paragraph(shift_str, cell_style),
            Paragraph(clean_status, cell_style)
        ])

    pdf_table = Table(table_data, colWidths=[260, 70, 70, 50, 100], repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
    ]))

    story.append(pdf_table)
    doc.build(story)
    buffer.seek(0)
    return buffer


if file_m1 and file_m2:
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

        m1_sub = df_m1[df_m1['Engine'] == selected_engine][['Keyword', 'Ranking']].rename(columns={'Ranking': 'Prev_Ranking'})
        m2_sub = df_m2[df_m2['Engine'] == selected_engine][['Keyword', 'Ranking']].rename(columns={'Ranking': 'Curr_Ranking'})

        merged = pd.merge(m1_sub, m2_sub, on='Keyword', how='outer')

        merged['Prev_Ranking'] = merged['Prev_Ranking'].fillna(100).astype(int)
        merged['Curr_Ranking'] = merged['Curr_Ranking'].fillna(100).astype(int)

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

        curr_ranks = merged['Curr_Ranking']
        top_1_3 = len(merged[(curr_ranks >= 1) & (curr_ranks <= 3)])
        top_4_10 = len(merged[(curr_ranks >= 4) & (curr_ranks <= 10)])
        top_11_30 = len(merged[(curr_ranks >= 11) & (curr_ranks <= 30)])
        out_serp = len(merged[curr_ranks >= 100])

        ranked_keywords = merged[curr_ranks < 100]
        avg_pos = round(ranked_keywords['Curr_Ranking'].mean(), 1) if not ranked_keywords.empty else "N/A"

        st.subheader(f"SEO Performance Overview ({selected_engine})")

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

        status_filter = st.multiselect("Filter by Status:", merged['Status'].unique(), default=merged['Status'].unique())
        filtered_df = merged[merged['Status'].isin(status_filter)].sort_values(by='Position Shift', ascending=False)

        display_df = filtered_df.rename(columns={
            'Prev_Ranking': label_m1,
            'Curr_Ranking': label_m2
        })

        display_df.index = range(1, len(display_df) + 1)

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
