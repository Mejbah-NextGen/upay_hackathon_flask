"""Read a consistent SQLite snapshot and print every table, row and column.

This administrator-only CLI deliberately lives outside the wallet's user routes.
The PDF includes an exact JSON attachment alongside its readable table sections.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import closing
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, LongTable, PageBreak, PageTemplate, Paragraph,
    Spacer, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
BD = timezone(timedelta(hours=6))
NAVY = colors.HexColor("#152942")
BLUE = colors.HexColor("#075dc6")
PALE = colors.HexColor("#f0f5fb")
MUTED = colors.HexColor("#596b81")
MONEY_COLUMNS = frozenset({
    "balance", "opening_balance", "amount", "fee", "monthly_amount", "outstanding",
    "contribution_total", "estimated_return",
})


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def read_snapshot(database):
    """No app imports, bootstrap seeding, writes, or omitted internal tables."""
    database = Path(database).resolve(strict=True)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        schema = source.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        tables = []
        for name, sql in schema:
            info = source.execute(f"PRAGMA table_info({identifier(name)})").fetchall()
            columns = [item[1] for item in info]
            primary = [item[1] for item in sorted(info, key=lambda item: item[5]) if item[5]]
            order = primary or columns
            query = f"SELECT * FROM {identifier(name)}"
            if order:
                query += " ORDER BY " + ", ".join(map(identifier, order))
            rows = source.execute(query).fetchall()
            tables.append({
                "name": name, "schema": sql or "", "columns": columns,
                "types": [item[2] for item in info], "primary_key": primary,
                "rows": [[json_value(cell) for cell in row] for row in rows],
            })
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = source.execute("PRAGMA foreign_key_check").fetchall()
    return {
        "format": "upayx-complete-database-snapshot-v1", "source": database.name,
        "generated_at_bangladesh": datetime.now(BD).isoformat(timespec="seconds"),
        "integrity_check": integrity, "foreign_key_violations": foreign_keys,
        "tables": tables,
    }


def json_value(value):
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    return value


def text_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, dict):
        return "BASE64:" + value["data"]
    if value == "":
        return '"" (empty string)'
    return str(value)


def styles():
    regular = "Helvetica"
    bold = "Helvetica-Bold"
    for candidate in ("C:/Windows/Fonts/Nirmala.ttc", "C:/Windows/Fonts/arial.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("DatabaseBody", candidate))
            regular = "DatabaseBody"
            break
    result = getSampleStyleSheet()
    specifications = {
        "Cover": dict(fontName=bold, fontSize=29, leading=35, textColor=NAVY, spaceAfter=16),
        "Section": dict(fontName=bold, fontSize=17, leading=22, textColor=NAVY, spaceAfter=12),
        "Subsection": dict(fontName=bold, fontSize=11, leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=8),
        "Copy": dict(fontName=regular, fontSize=10, leading=15, textColor=NAVY, spaceAfter=9),
        "Fine": dict(fontName=regular, fontSize=8, leading=11, textColor=MUTED, spaceAfter=5),
        "Cell": dict(fontName=regular, fontSize=7.6, leading=10.4, textColor=NAVY, wordWrap="CJK"),
        "CellNumber": dict(fontName=regular, fontSize=7.6, leading=10.4, textColor=NAVY, alignment=2, wordWrap="CJK"),
        "CellHead": dict(fontName=bold, fontSize=7.7, leading=10.6, textColor=colors.white, wordWrap="CJK"),
        "TOC": dict(fontName=regular, fontSize=9, leading=12, textColor=NAVY, leftIndent=0, firstLineIndent=0, spaceBefore=0, spaceAfter=0),
    }
    for name, options in specifications.items():
        result.add(ParagraphStyle(name, **options))
    for name in ("Copy", "Fine", "Cell", "CellNumber"):
        result[name].shaping = 1
    return result


def paragraph(value, style):
    return Paragraph(escape(text_value(value)).replace("\n", "<br/>"), style)


def table(rows, widths, sheet, numeric_columns=()):
    data = [[paragraph(cell, sheet["CellHead"] if index == 0 else
                       sheet["CellNumber"] if column in numeric_columns else sheet["Cell"])
             for column, cell in enumerate(row)] for index, row in enumerate(rows)]
    result = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT",
                       splitByRow=1, splitInRow=1)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 0), (-1, 0), 1, BLUE),
        ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#dce4ee")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for index in numeric_columns:
        commands.append(("ALIGN", (index, 1), (index, -1), "RIGHT"))
    result.setStyle(TableStyle(commands))
    return result


def column_groups(columns):
    """Repeat a stable PDF row number to join wide tables without clipping."""
    return [list(range(start, min(start + 5, len(columns))))
            for start in range(0, len(columns), 5)]


def column_widths(headers, data, available):
    weights = []
    for index, name in enumerate(headers):
        sample_length = max([len(str(name))] + [len(text_value(row[index])) for row in data])
        if index == 0:
            weight = 4
        elif name in {"id", "user_id", "transaction_id", "verified", "months", "auto_pay"}:
            weight = 6
        elif any(word in name for word in ("note", "reason", "error", "schema", "fingerprint")):
            weight = min(40, max(22, sample_length / 2.3))
        elif any(word in name for word in ("created", "executed", "due_at", "updated", "repaid")):
            weight = 21
        else:
            weight = min(28, max(12, sample_length / 1.5))
        weights.append(weight)
    # Keep the shared record label readable, even when other fields are long.
    # This also leaves room for three-digit row numbers in the full ledger.
    first_width = 46
    scale = (available - first_width) / sum(weights[1:])
    return [first_width] + [weight * scale for weight in weights[1:]]


class DatabaseDocument(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "Section":
            label = flowable.getPlainText()
            anchor = "section-" + hashlib.sha256(label.encode()).hexdigest()[:12]
            self.canv.bookmarkPage(anchor)
            self.canv.addOutlineEntry(label, anchor, level=0, closed=False)
            self.notify("TOCEntry", (0, label, self.page, anchor))


def export_pdf(database, output):
    snapshot = read_snapshot(database)
    if snapshot["integrity_check"] != "ok" or snapshot["foreign_key_violations"]:
        raise ValueError("Database failed integrity or foreign-key checks; report was not generated.")
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    output = Path(output).resolve()
    if output == Path(database).resolve():
        raise ValueError("The output must not overwrite the database.")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet = styles()
    width, height = landscape(A4)
    usable = width - 72
    story = [Spacer(1, 27), paragraph("UpayX", sheet["Subsection"]),
             paragraph("Complete database\ntable report", sheet["Cover"]),
             paragraph("120-day hackathon dataset | Clearly labelled synthetic records", sheet["Copy"]),
             paragraph("This administrator report includes every SQLite table, every row and every column in one consistent snapshot. It includes all accounts and is intended for project review, not as a customer statement.", sheet["Copy"]),
             Spacer(1, 8)]
    transactions = next((item for item in snapshot["tables"] if item["name"] == "transactions"), None)
    dates = []
    if transactions and "created_at" in transactions["columns"]:
        date_index = transactions["columns"].index("created_at")
        for row in transactions["rows"]:
            if row[date_index]:
                moment = datetime.fromisoformat(row[date_index])
                dates.append(moment.replace(tzinfo=timezone.utc).astimezone(BD).date())
    summary = [
        ["Snapshot detail", "Value"],
        ["Database", snapshot["source"]],
        ["Tables / total rows", f"{len(snapshot['tables'])} / {sum(len(item['rows']) for item in snapshot['tables'])}"],
        ["Transaction dates (Bangladesh)", f"{min(dates)} through {max(dates)} ({(max(dates) - min(dates)).days + 1} calendar days)" if dates else "No ledger records"],
        ["SQLite integrity / foreign keys", "OK / no violations"],
        ["Snapshot generated (Bangladesh)", snapshot["generated_at_bangladesh"]],
        ["Exact snapshot attachment", "database_snapshot.json (embedded in this PDF)"],
        ["Attachment SHA-256", digest],
    ]
    story.append(table(summary, [190, usable - 190], sheet))
    story += [Spacer(1, 12), paragraph("Dates in raw database fields are stored UTC; the range above is converted to Bangladesh time (UTC+6). Monetary fields are labelled BDT and formatted to two decimals; the attachment preserves their exact raw values. NULL and empty strings are distinguished. Binary fields use complete base64. Wide tables share the same PDF row number across column groups so no fields are dropped.", sheet["Fine"]), PageBreak(),
              paragraph("Table directory", sheet["Section"])]
    toc = TableOfContents()
    toc.levelStyles = [sheet["TOC"]]
    story += [toc, PageBreak(), paragraph("Database inventory", sheet["Section"]),
              paragraph("Every stored table is included below. Row counts include all accounts, statuses and administrative records.", sheet["Fine"])]
    coverage = [["Table", "Rows", "Columns", "Primary key"]]
    coverage += [[item["name"], len(item["rows"]), len(item["columns"]), ", ".join(item["primary_key"]) or "None"] for item in snapshot["tables"]]
    story.append(table(coverage, [275, 75, 75, usable - 425], sheet))
    for item in snapshot["tables"]:
        story += [PageBreak(), paragraph(item["name"], sheet["Section"]),
                  paragraph(f"{len(item['rows'])} rows | {len(item['columns'])} columns | Primary key: {', '.join(item['primary_key']) or 'none'}", sheet["Fine"]),
                  paragraph("Column definitions", sheet["Subsection"])]
        definitions = [["Column", "SQLite type", "Primary key"]]
        definitions += [[name, declared or "Undeclared", "Yes" if name in item["primary_key"] else ""] for name, declared in zip(item["columns"], item["types"])]
        story.append(table(definitions, [usable * .45, usable * .35, usable * .20], sheet))
        story += [paragraph("Exact CREATE TABLE statement", sheet["Subsection"]), paragraph(item["schema"], sheet["Fine"])]
        if not item["rows"]:
            story.append(paragraph("No rows in this snapshot. The empty table is included intentionally.", sheet["Copy"]))
            continue
        for group_index, group in enumerate(column_groups(item["columns"]), 1):
            names = [item["columns"][index] for index in group]
            headers = ["PDF row"] + [name + " (BDT)" if name in MONEY_COLUMNS else name for name in names]
            body = [[number] + [f"{Decimal(str(row[index])):,.2f}" if item["columns"][index] in MONEY_COLUMNS and row[index] is not None else row[index]
                                for index in group] for number, row in enumerate(item["rows"], 1)]
            numeric = [0] + [number + 1 for number, index in enumerate(group)
                             if item["columns"][index] in MONEY_COLUMNS or item["types"][index].upper() in {"INTEGER", "NUMERIC", "BOOLEAN"}]
            if group_index > 1:
                story.append(PageBreak())
            story += [paragraph(f"{item['name']} - data group {group_index} / {len(column_groups(item['columns']))}", sheet["Subsection"]),
                      paragraph("PDF row identifies the same record across all column groups in this table.", sheet["Fine"]),
                      table([headers] + body, column_widths(["PDF row"] + names, body, usable), sheet, numeric_columns=numeric)]
    story += [PageBreak(), paragraph("Snapshot verification", sheet["Section"]),
              paragraph("The PDF is a readable view of the exact attached JSON snapshot. All source rows appear in each relevant column group. No SQL table, stored field, unsuccessful record or other account has been filtered out. The attachment preserves original SQLite numeric/string/null values and complete base64 for binary cells.", sheet["Copy"]),
              paragraph("To extract the attachment", sheet["Subsection"]),
              paragraph("Open the PDF attachments panel in a compatible reader and save database_snapshot.json. Compare its SHA-256 with the cover value. Regenerate the report after database changes; this artifact records the state at its generation time.", sheet["Copy"]),
              paragraph("Synthetic data provenance", sheet["Subsection"]),
              paragraph("Generated for the UpayX local hackathon prototype. This is not a real upay customer export and has no live bank, payment, credit or identity integrations. Demo fees, account records and financial terms illustrate project behavior. Backup files are recovery copies and are intentionally outside this database snapshot.", sheet["Copy"])]

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFillColor(BLUE)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(36, height - 30, "UpayX")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - 36, height - 28, "COMPLETE DATABASE | SYNTHETIC DEMO")
        canvas.setStrokeColor(colors.HexColor("#dce4ee"))
        canvas.line(36, height - 39, width - 36, height - 39)
        canvas.line(36, 33, width - 36, 33)
        canvas.drawString(36, 20, "Administrator snapshot | Monetary fields: BDT | Raw timestamps: UTC")
        canvas.drawRightString(width - 36, 20, f"Page {document.page}")
        canvas.restoreState()

    document = DatabaseDocument(str(output), pagesize=(width, height),
                                leftMargin=36, rightMargin=36, topMargin=52,
                                bottomMargin=44, title="UpayX complete database table report",
                                author="UpayX hackathon project")
    document.addPageTemplates(PageTemplate(id="database", frames=[Frame(36, 44, usable, height - 96, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=decorate))
    document.multiBuild(story)
    reader = PdfReader(output)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_attachment("database_snapshot.json", payload)
    with output.open("wb") as destination:
        writer.write(destination)
    check = PdfReader(output)
    attached = check.attachments["database_snapshot.json"][0]
    if hashlib.sha256(attached).hexdigest() != digest:
        raise ValueError("PDF attachment verification failed.")
    return {"pdf": str(output), "pages": len(check.pages), "tables": len(snapshot["tables"]),
            "rows": sum(len(item["rows"]) for item in snapshot["tables"]), "snapshot_sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "upay_hackathon.db")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "pdf" / "UPAYX_DATABASE_REPORT.pdf")
    args = parser.parse_args()
    print(json.dumps(export_pdf(args.database, args.output), indent=2))


if __name__ == "__main__":
    main()
