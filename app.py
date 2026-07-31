def generate_pdf_report(dataframe, engine_name, label_m1, label_m2):
    """Generates a downloadable PDF document with custom dynamic month column headers."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    
    # Create a custom subtitle style safely
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
