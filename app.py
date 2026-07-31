import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
import os
import requests
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from svglib.svglib import svg2rlg

# ----------------------------------------------------
# 📌 CONFIGURATION: Growth99 Fixed SVG Logo URL (LINE 16)
# ----------------------------------------------------
FIXED_LOGO_PATH = "https://growth99.com/storage/2024/09/LOGO.svg"

# Page Configuration
st.set_page_config(page_title="SE Ranking Comparison Tool", layout="wide")

# Inject CSS for seamless Theme-Adaptive UI (Light & Dark Theme Compatible)
st.markdown("""
    <style>
        /* Card styling using Streamlit CSS variables for perfect light/dark theme contrast */
        div[data-testid="stMetric"] {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 10px;
            padding: 12px 16px;
            box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.05);
        }
        
        [data-testid="stMetricLabel"] {
            color: var(--text-color) !important;
            opacity: 0.8;
            font-weight: 500;
        }

        [data-testid="stMetricValue"] {
            color: var(--text-color) !important;
            font-size: 1.6rem !important;
            font-weight: 700;
        }
    </style>
""", unsafe_allow_html=True)

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
    """Cleans raw PDF text into a valid rank string. Returns '-' if unranked/missing."""
    if not val_str:
        return "-"
    
    val = re.sub(r'[^\d\->]', '', str(val_str)).strip()
    
    if not val or val == '-' or '>' in val:
        return "-"
    
    if val.isdigit():
        num = int(val)
        if 1 <= num <= 100:
            return str(num)
        else:
            return "-"
            
    return "-"


def parse_se_ranking_tables(pdf_file):
    """Extracts tables across all pages using pdfplumber."""
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

                    # Filter out headers, summary blocks, and "100% Keywords in SERPs" text
                    kw_lower = kw.lower()
                    if kw_lower in ['keyword', 'results', 'baseline', 'ranking', ''] or 'brief rankings history' in kw_lower:
                        continue
                    if 'rankings overview' in kw_lower or kw.startswith('General') or 'keywords in serp' in kw_lower:
                        continue

                    rank_val = "-"
                    for col_idx in [2, 3, 1]:
                        if col_idx < len(clean_row):
                            potential_val = clean_row[col_idx]
                            parsed_rank = clean_rank_value(potential_val)
                            if parsed_rank != "-":
                                rank_val = parsed_rank
                                break

                    extracted_rows.append({
                        'Engine': current_engine,
                        'Keyword': kw,
                        'Ranking': rank_val
                    })

    if not extracted_rows:
        return None

    df = pd.DataFrame(extracted_rows)
    df = df.drop_duplicates(subset=['Engine', 'Keyword'], keep='first')
    return df


def get_fixed_logo_image():
    """Loads and converts the SVG logo from URL or local path for ReportLab compatibility."""
    try:
        if FIXED_LOGO_PATH.lower().endswith('.svg'):
            if FIXED_LOGO_PATH.startswith("http://") or FIXED_LOGO_PATH.startswith("https://"):
                response = requests.get(FIXED_LOGO_PATH)
                if response.status_code == 200:
                    svg_data = io.BytesIO(response.content)
                    drawing = svg2rlg(svg_data)
            elif os.path.exists(FIXED_LOGO_PATH):
                drawing = svg2rlg(FIXED_LOGO_PATH)
            
            if drawing:
                # Scale drawing proportionally to fit header dimensions (130x40)
                target_width = 130
                scale_factor = target_width / float(drawing.width)
                drawing.width *= scale_factor
                drawing.height *= scale_factor
                drawing.scale(scale_factor, scale_factor)
                return drawing

        # Standard Raster Formats (PNG, JPG)
        elif FIXED_LOGO_PATH.startswith("http://") or FIXED_LOGO_PATH.startswith("https://"):
            response = requests.get(FIXED_LOGO_PATH)
            if response.status_code == 200:
                img_data = io.BytesIO(response.content)
                return Image(img_data, width=130, height=40)
        elif os.path.exists(FIXED_LOGO_PATH):
            return Image(FIXED_LOGO_PATH, width=130, height=40)

    except Exception as e:
        st.warning(f"Could not load logo: {e}")
    return ""


def generate_pdf_report(dataframe, project_name, project_url, engine_name, label_m1, label_m2):
    """Generates downloadable PDF document with project details, fixed Growth99 SVG logo, and ranking metrics."""
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
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#4b5563')
    )

    cell_style = ParagraphStyle('TableCell', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.black)
    
    header_cell_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    metric_label_style = ParagraphStyle('MetricLabel', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#9ca3af'), alignment=1)
    metric_val_style = ParagraphStyle('MetricVal', parent=styles['Normal'], fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)

    # Clean engine name to remove "Google" prefix for header title
    clean_engine_name = re.sub(r'(?i)\bgoogle\b\s*', '', engine_name).strip()

    # Header Construction: Title/Subtitle on Left, Fixed SVG Logo on Right
    title_text = f"Keyword Ranking Comparison Report - {clean_engine_name}"
    subtitle_text = (
        f"<b>Project Name:</b> {project_name}<br/>"
        f"<b>Project URL:</b> {project_url}<br/>"
        f"<b>Period:</b> {label_m1} vs {label_m2}"
    )

    left_header_flowables = [
        Paragraph(title_text, title_style),
        Paragraph(subtitle_text, subtitle_style)
    ]

    logo_img = get_fixed_logo_image()
    if hasattr(logo_img, 'hAlign'):
        logo_img.hAlign = 'RIGHT'

    header_table_data = [[left_header_flowables, logo_img]]
    header_table = Table(header_table_data, colWidths=[412, 160])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    story.append(header_table)
    story.append(Spacer(1, 12))

    # Calculate Overview Metrics
    curr_numeric = pd.to_numeric(dataframe['Curr_Ranking'], errors='coerce')

    total_kw = len(dataframe)
    top_1_3 = len(dataframe[(curr_numeric >= 1) & (curr_numeric <= 3)])
    top_4_10 = len(dataframe[(curr_numeric >= 4) & (curr_numeric <= 10)])
    top_11_30 = len(dataframe[(curr_numeric >= 11) & (curr_numeric <= 30)])

    valid_ranks = curr_numeric.dropna()
    avg_pos = round(valid_ranks.mean(), 1) if not valid_ranks.empty else "N/A"

    shifts = dataframe['Position Shift']
    improved = len(dataframe[shifts > 0])
    dropped = len(dataframe[shifts < 0])
    new_kw = len(dataframe[dataframe['Status'].str.contains("New Keyword", na=False)])
    kw_missing = len(dataframe[dataframe['Status'].str.contains("Keyword Missing", na=False)])

    # Metrics Summary Table
    metrics_data = [
        [
            Paragraph("Total Keywords", metric_label_style),
            Paragraph("Top 1-3", metric_label_style),
            Paragraph("Top 4-10", metric_label_style),
            Paragraph("Top 11-30", metric_label_style),
            Paragraph("Avg. Position", metric_label_style)
        ],
        [
            Paragraph(str(total_kw), metric_val_style),
            Paragraph(str(top_1_3), metric_val_style),
            Paragraph(str(top_4_10), metric_val_style),
            Paragraph(str(top_11_30), metric_val_style),
            Paragraph(str(avg_pos), metric_val_style)
        ],
        [
            Paragraph("Improved Positions", metric_label_style),
            Paragraph("Dropped Positions", metric_label_style),
            Paragraph("New Keywords", metric_label_style),
            Paragraph("Keyword Missing", metric_label_style),
            Paragraph("", metric_label_style)
        ],
        [
            Paragraph(str(improved), metric_val_style),
            Paragraph(str(dropped), metric_val_style),
            Paragraph(str(new_kw), metric_val_style),
            Paragraph(str(kw_missing), metric_val_style),
            Paragraph("", metric_val_style)
        ]
    ]

    metrics_table = Table(metrics_data, colWidths=[114, 114, 114, 114, 114])
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

    # Keyword Comparison Table
    m1_header = f"{label_m1} Rank" if "Rank" not in label_m1 else label_m1
    m2_header = f"{label_m2} Rank" if "Rank" not in label_m2 else label_m2

    table_data = [[
        Paragraph("<b>Keyword</b>", header_cell_style),
        Paragraph(f"<b>{m1_header}</b>", header_cell_style),
        Paragraph(f"<b>{m2_header}</b>", header_cell_style),
        Paragraph("<b>Shift</b>", header_cell_style),
        Paragraph("<b>Status</b>", header_cell_style)
    ]]

    for _, row in dataframe.iterrows():
        clean_status = str(row['Status']).replace("🆕 ", "").replace("❌ ", "").replace("🟢 ", "").replace("🔴 ", "").replace("⚪ ", "")
        
        shift_val = row['Position Shift']
        if pd.isna(shift_val) or shift_val == "":
            shift_str = "-"
        else:
            shift_num = int(shift_val)
            shift_str = f"+{shift_num}" if shift_num > 0 else str(shift_num)

        prev_rank_str = str(row['Prev_Ranking']) if str(row['Prev_Ranking']) != "" else "-"
        curr_rank_str = str(row['Curr_Ranking']) if str(row['Curr_Ranking']) != "" else "-"

        table_data.append([
            Paragraph(str(row['Keyword']), cell_style),
            Paragraph(prev_rank_str, cell_style),
            Paragraph(curr_rank_str, cell_style),
            Paragraph(shift_str, cell_style),
            Paragraph(clean_status, cell_style)
        ])

    pdf_table = Table(table_data, colWidths=[260, 70, 70, 50, 100], repeatRows=1)
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
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

    st.sidebar.subheader("⚙️ Report Settings")
    project_name = st.sidebar.text_input("Project / Client Name:", value="My Website Project")
    project_url = st.sidebar.text_input("Project URL:", value="https://example.com")
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

        merged['Prev_Ranking'] = merged['Prev_Ranking'].fillna("-")
        merged['Curr_Ranking'] = merged['Curr_Ranking'].fillna("-")

        prev_num = pd.to_numeric(merged['Prev_Ranking'], errors='coerce')
        curr_num = pd.to_numeric(merged['Curr_Ranking'], errors='coerce')

        def calc_shift(row):
            p = row['prev_num']
            c = row['curr_num']
            if pd.notna(p) and pd.notna(c):
                return int(p - c)
            return None

        temp_calc = pd.DataFrame({'prev_num': prev_num, 'curr_num': curr_num})
        merged['Position Shift'] = temp_calc.apply(calc_shift, axis=1)

        def get_status(row):
            p = row['prev_num']
            c = row['curr_num']
            
            if pd.isna(p) and pd.notna(c):
                return "🆕 New Keyword"
            elif pd.notna(p) and pd.isna(c):
                return "❌ Keyword Missing"
            elif pd.notna(p) and pd.notna(c):
                shift = p - c
                if shift > 0:
                    return "🟢 Improved"
                elif shift < 0:
                    return "🔴 Dropped"
                else:
                    return "⚪ No Change"
            else:
                return "⚪ No Data"

        temp_calc['prev_num'] = prev_num
        temp_calc['curr_num'] = curr_num
        merged['Status'] = temp_calc.apply(get_status, axis=1)

        # Filters Section
        filter_col1, filter_col2 = st.columns([1, 2])

        with filter_col1:
            status_filter = st.multiselect("Filter by Status:", merged['Status'].unique(), default=merged['Status'].unique())

        with filter_col2:
            keywords_to_remove = st.multiselect("🗑️ Select Keywords to Remove/Delete:", merged['Keyword'].unique())

        # Apply Filters (Status + Keyword Removal)
        filtered_df = merged[
            (merged['Status'].isin(status_filter)) & 
            (~merged['Keyword'].isin(keywords_to_remove))
        ].copy()

        # Recalculate Overview Metrics based on filtered dataset
        curr_num_filtered = pd.to_numeric(filtered_df['Curr_Ranking'], errors='coerce')
        top_1_3 = len(filtered_df[(curr_num_filtered >= 1) & (curr_num_filtered <= 3)])
        top_4_10 = len(filtered_df[(curr_num_filtered >= 4) & (curr_num_filtered <= 10)])
        top_11_30 = len(filtered_df[(curr_num_filtered >= 11) & (curr_num_filtered <= 30)])

        valid_curr = curr_num_filtered.dropna()
        avg_pos = round(valid_curr.mean(), 1) if not valid_curr.empty else "N/A"

        st.subheader(f"📌 {project_name} ({project_url}) - SEO Overview ({selected_engine})")

        r1_col1, r1_col2, r1_col3, r1_col4, r1_col5 = st.columns(5)
        r1_col1.metric("Total Keywords", len(filtered_df))
        r1_col2.metric("Top 1-3", top_1_3)
        r1_col3.metric("Top 4-10", top_4_10)
        r1_col4.metric("Top 11-30", top_11_30)
        r1_col5.metric("Avg. Position", avg_pos)

        r2_col1, r2_col2, r2_col3, r2_col4 = st.columns(4)
        r2_col1.metric("Improved Positions", len(filtered_df[filtered_df['Position Shift'] > 0]))
        r2_col2.metric("Dropped Positions", len(filtered_df[filtered_df['Position Shift'] < 0]))
        r2_col3.metric("New Keywords", len(filtered_df[filtered_df['Status'] == "🆕 New Keyword"]))
        r2_col4.metric("Keyword Missing", len(filtered_df[filtered_df['Status'] == "❌ Keyword Missing"]))

        st.markdown("---")
        
        filtered_df['Position Shift Display'] = filtered_df['Position Shift'].apply(
            lambda x: "-" if pd.isna(x) or x == "" else (f"+{int(x)}" if int(x) > 0 else str(int(x)))
        )

        filtered_df['sort_helper'] = filtered_df['Position Shift'].fillna(-999)
        filtered_df = filtered_df.sort_values(by='sort_helper', ascending=False).drop(columns=['sort_helper'])

        display_df = filtered_df.copy()
        display_df['Position Shift'] = display_df['Position Shift Display']
        display_df = display_df.drop(columns=['Position Shift Display'])

        display_df = display_df.rename(columns={
            'Prev_Ranking': label_m1,
            'Curr_Ranking': label_m2
        })

        display_df.index = range(1, len(display_df) + 1)

        head_col1, head_col2 = st.columns([4, 1])
        head_col1.subheader("Keyword Comparison Data")

        # Dynamic File Name
        clean_project = re.sub(r'[^\w\s-]', '', project_name).strip().replace(' ', '_')
        clean_m1 = re.sub(r'[^\w\s-]', '', label_m1).strip().replace(' ', '_')
        clean_m2 = re.sub(r'[^\w\s-]', '', label_m2).strip().replace(' ', '_')
        clean_engine = re.sub(r'[^\w\s-]', '', selected_engine).strip().replace(' ', '_')
        current_date = datetime.today().strftime('%Y-%m-%d')

        dynamic_filename = f"{clean_project}_{clean_m1}_vs_{clean_m2}_{clean_engine}_{current_date}.pdf"

        # Generate PDF
        pdf_bytes = generate_pdf_report(
            filtered_df, 
            project_name, 
            project_url, 
            selected_engine, 
            label_m1, 
            label_m2
        )
        
        head_col2.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=dynamic_filename,
            mime="application/pdf"
        )

        st.dataframe(display_df, use_container_width=True)
    else:
        st.error("Could not find table data in the uploaded PDFs. Please check that both files contain the Brief Rankings History table.")
