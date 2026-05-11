import os
import sys
import argparse
from pathlib import Path
import fitz  # PyMuPDF
from archive_to_zenodo import archive_document
import subprocess
import shutil
import re

SOCIETY_STRINGS = [
    "Royal Netherlands Astronomical Society",
    "Koninklijke Nederlandse Astronomenclub",
    "Office of the Secretary",
    "Het Kantoor van de Secretaris",
    "Executive Committee of the Board",
    "Marijke Haverkorn",
    "Jake Noel-Storr",
    "Steven Rieder",
    "Peter Barthel",
    "Ralph Wijers",
    "KvK: 40047819",
    "www.kna-rnas.nl",
    "The one-and-only professional organization",
    "Please visit the website"
]

def extract_structural_text(doc_path):
    """Uses Pandoc to extract structural RST from Word/ODT files."""
    print(f"Running Pandoc on {doc_path}...")
    try:
        # Convert to rst
        result = subprocess.run(
            ["pandoc", str(doc_path), "--from", "docx" if doc_path.suffix == ".docx" else "odt", "--to", "rst"],
            capture_output=True, text=True, check=True
        )
        text = result.stdout
        
        # Post-process Pandoc output for our specific needs
        # 1. Ensure blank lines between list items for translation isolation
        # Pandoc often groups list items together. We want to force space.
        lines = text.splitlines()
        processed_lines = []
        for i, line in enumerate(lines):
            processed_lines.append(line)
            # If line starts with a list marker and next line exists and is not empty, add a blank line
            # This is a bit naive but works for simple lists
            if re.match(r'^\d+\.', line.strip()) and i + 1 < len(lines) and lines[i+1].strip():
                processed_lines.append("")
        
        return "\n".join(processed_lines)
    except Exception as e:
        print(f"Pandoc conversion failed: {e}")
        return None

def generate_pdf_from_doc(doc_path, output_dir):
    """Uses LibreOffice to generate a PDF version of the document."""
    print(f"Generating PDF via LibreOffice...")
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", str(doc_path), "--outdir", str(output_dir)],
            check=True
        )
        pdf_path = output_dir / f"{doc_path.stem}.pdf"
        return pdf_path
    except Exception as e:
        print(f"PDF generation failed: {e}")
        return None

def extract_premium_text_from_pdf(pdf_path):
    """Legacy coordinate-based PDF extractor (Fallback)."""
    doc = fitz.open(pdf_path)
    raw_spans = []
    
    for i, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        page_height = page.rect.height
        
        for b in blocks:
            if b['type'] != 0: continue
            for l in b['lines']:
                for s in l['spans']:
                    y0 = s['bbox'][1]
                    text_s = s['text'].strip()
                    if not text_s: continue
                    
                    is_list_marker = re.match(r'^(\d+(?:\.\d+)*\.|[a-z]\.|[ivx]+\.)', text_s.lower())
                    is_society_blob = any(soc.lower() in text_s.lower() for soc in SOCIETY_STRINGS)
                    is_in_margin = y0 < 180 or y0 > (page_height - 100)
                    
                    if (is_society_blob and not is_list_marker and len(text_s) < 150) or (is_in_margin and len(text_s) < 50):
                        continue
                    
                    raw_spans.append({
                        'text': text_s,
                        'x0': s['bbox'][0],
                        'y0': y0,
                        'size': round(s['size'], 1),
                        'bold': bool(s['flags'] & 2**4),
                    })

    if not raw_spans: return ""

    lines = []
    if raw_spans:
        curr_line = raw_spans[0]
        for s in raw_spans[1:]:
            if abs(s['y0'] - curr_line['y0']) < 3 and s['x0'] - (curr_line['x0'] + len(curr_line['text'])*4) < 120:
                curr_line['text'] += " " + s['text']
                curr_line['x0'] = min(curr_line['x0'], s['x0'])
                curr_line['size'] = max(curr_line['size'], s['size'])
                curr_line['bold'] = curr_line['bold'] or s['bold']
            else:
                lines.append(curr_line)
                curr_line = s
        lines.append(curr_line)

    blocks = []
    curr_block = None
    
    for l in lines:
        text = l['text'].strip()
        if not text: continue
        is_list_marker = re.match(r'^(\d+(?:\.\d+)*\.|[a-z]\.|[ivx]+\.)', text.lower())
        is_at_margin = l['x0'] < 80
        is_major_header = is_at_margin and l['size'] > 15
        is_minor_header = is_at_margin and l['size'] > 11 and l['bold'] and not is_list_marker and len(text) < 60
        indent_level = max(0, int((l['x0'] - 71) / 18))

        if is_major_header or is_minor_header:
            if curr_block: blocks.append(curr_block)
            blocks.append({'type': 'header', 'text': text, 'indent': 0, 'size': l['size']})
            curr_block = None
        elif is_list_marker:
            if curr_block: blocks.append(curr_block)
            blocks.append({'type': 'list', 'text': text, 'indent': indent_level})
            curr_block = None
        else:
            if curr_block and curr_block['type'] in ['paragraph', 'list'] and curr_block['indent'] == indent_level:
                curr_block['text'] += " " + text
            else:
                if curr_block: blocks.append(curr_block)
                curr_block = {'type': 'paragraph', 'text': text, 'indent': indent_level}
                
    if curr_block: blocks.append(curr_block)

    rst_lines = []
    for b in blocks:
        if b['type'] == 'header':
            rst_lines.append("")
            rst_lines.append(b['text'])
            char = "=" if b['size'] > 17 else "-"
            rst_lines.append(char * len(b['text']))
            rst_lines.append("")
        elif b['type'] == 'list':
            indent = "   " * b['indent']
            rst_lines.append("")
            rst_lines.append(f"{indent}{b['text']}")
        elif b['type'] == 'paragraph':
            indent = "   " * b['indent']
            rst_lines.append("")
            rst_lines.append(f"{indent}{b['text']}")
            
    return "\n".join(rst_lines).strip()

def ingest_document(file_path, category, original_lang='en', title=None, description=None, publish=False, deposition_id=None):
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"Error: File not found {file_path}")
        return

    if not title: title = file_path.stem.replace("-", " ").replace("_", " ").title()
    
    file_stem = file_path.stem
    target_dir = Path(f"docs/source/{category}")
    target_dir.mkdir(parents=True, exist_ok=True)
    rst_path = target_dir / f"{file_stem}.rst"

    # 1. Determine Source & Extract Text
    if file_path.suffix.lower() in ['.docx', '.odt']:
        text = extract_structural_text(file_path)
        # Generate PDF for archive
        pdf_path = generate_pdf_from_doc(file_path, Path("docs/source/_static/archive"))
    elif file_path.suffix.lower() == '.pdf':
        print(f"Using legacy PDF extraction for {file_path}...")
        text = extract_premium_text_from_pdf(file_path)
        pdf_path = file_path
    else:
        print(f"Error: Unsupported file type {file_path.suffix}")
        return

    if not text:
        print("Error: Could not extract text from document.")
        return

    # 2. Archive to Zenodo
    print(f"Archiving to Zenodo (Publish={publish})...")
    creators = [{'name': 'KNA-RNAS Society', 'affiliation': 'KNA-RNAS'}]
    # We always use the PDF for Zenodo
    doi_or_id = archive_document(str(pdf_path), title, description or f"Official {category} document", creators, publish=publish, deposition_id=deposition_id)
    
    doi_display = f":doi:`{doi_or_id}`" if publish and not isinstance(doi_or_id, int) else f"Draft ID: {doi_or_id}"

    # 3. Ensure PDF is in static archive
    downloads_dir = Path("docs/source/_static/archive")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target_pdf_abs = (downloads_dir / pdf_path.name).resolve()
    if pdf_path.resolve() != target_pdf_abs:
        shutil.copy(pdf_path, target_pdf_abs)

    rel_path_to_static = "../" * len(category.split('/')) + "_static/archive/" + pdf_path.name

    rst_content = f"""{title}
{"=" * len(title)}

.. document-of-record::
   :original-lang: {original_lang}

.. note::

   **Archived DOI**: {doi_display}

   .. button-link:: {rel_path_to_static}
      :color: primary
      :outline:
      :shadow:

      Download Original PDF

{text}

.. document-status::
   :approved: true
   :approved_in: Automated Ingestion
"""

    with open(rst_path, "w") as f: f.write(rst_content)
    print(f"Created RST file at {rst_path}")

    # 4. Synchronize translations
    print("\nRunning translation update...")
    try:
        docs_dir = Path("docs")
        venv_bin = Path(".venv/bin").resolve()
        subprocess.run([str(venv_bin / "sphinx-build"), "-b", "gettext", "source", "build/gettext"], cwd=docs_dir, check=True)
        subprocess.run([str(venv_bin / "sphinx-intl"), "update", "-p", "build/gettext", "-l", "nl"], cwd=docs_dir, check=True)
        subprocess.run([str(venv_bin / "python3"), "scripts/translate_docs.py"], check=True)
    except Exception as e:
        print(f"Translation sync failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument("--category", default="minutes")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--title")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--deposition-id", help="Zenodo deposition ID to update (instead of creating new)")
    args = parser.parse_args()
    ingest_document(args.file_path, args.category, args.lang, args.title, publish=args.publish, deposition_id=args.deposition_id)
