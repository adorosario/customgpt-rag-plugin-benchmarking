"""Convert .txt email tiers to .pdf format for PDF benchmark testing."""

import argparse
from pathlib import Path
from fpdf import FPDF


def txt_to_pdf(txt_path: Path, pdf_path: Path):
    """Convert a single .txt file to .pdf."""
    text = txt_path.read_text(encoding="utf-8", errors="replace")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=10)

    for line in text.split("\n"):
        safe_line = line.encode("latin-1", "replace").decode("latin-1")
        if line.startswith(("From:", "To:", "CC:", "Date:", "Subject:")):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 5, safe_line, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
        elif line.strip() == "":
            pdf.ln(3)
        else:
            # Wrap long lines safely
            pdf.multi_cell(0, 5, safe_line, new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))


def convert_tier(txt_tier_dir: Path, pdf_tier_dir: Path):
    """Convert all .txt files in a tier to .pdf in a new directory."""
    pdf_tier_dir.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(txt_tier_dir.glob("*.txt"))
    for txt_file in txt_files:
        pdf_file = pdf_tier_dir / txt_file.name.replace(".txt", ".pdf")
        txt_to_pdf(txt_file, pdf_file)

    return len(txt_files)


def main():
    parser = argparse.ArgumentParser(description="Convert .txt email tiers to .pdf")
    parser.add_argument("--input", default="emails", help="Base directory with tier_N folders")
    parser.add_argument("--output", default="emails_pdf", help="Output directory for PDF tiers")
    parser.add_argument("--max-tier", type=int, default=500, help="Max tier to convert")
    args = parser.parse_args()

    input_base = Path(args.input)
    output_base = Path(args.output)

    # Find all tier directories
    tier_dirs = sorted(input_base.glob("tier_*"), key=lambda p: int(p.name.split("_")[1]))

    for tier_dir in tier_dirs:
        tier_num = int(tier_dir.name.split("_")[1])
        if tier_num > args.max_tier:
            continue

        pdf_dir = output_base / tier_dir.name
        print(f"Converting {tier_dir.name}...", end=" ", flush=True)
        count = convert_tier(tier_dir, pdf_dir)
        print(f"{count} PDFs")

    print("Done!")


if __name__ == "__main__":
    main()
