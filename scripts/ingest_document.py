import os
import sys
import argparse
from pathlib import Path
import fitz  # PyMuPDF
from archive_to_zenodo import archive_document
import subprocess
import shutil
import re

# Common Society Strings to identify headers/footers
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
    "www.kna-rnas.nl"
]

def get_list_indent(text):
    """Return the correct indentation string for a list item."""
    text_lower = text.strip().lower()
    if re.match(r'^\d+\.', text_lower):
        return ""
    if re.match(r'^[ivx]+\.', text_lower):
        return "      "
    if re.match(r'^[a-z]\.', text_lower):
        return "   "
    return None

def is_list_item(text):
    return get_list_indent(text) is not None

def format_as_rst(blocks, is_footer=False, is_header_area=False):
    """Convert extracted blocks into well-formatted RST using Line Blocks and Nested Lists."""
    rst_lines = []
    
    # Sort blocks by y-coordinate then x-coordinate
    blocks.sort(key=lambda b: (round(b['bbox'][1]), round(b['bbox'][0])))
    
    current_paragraph = []
    
    for i, b in enumerate(blocks):
        text_parts = []
        for line in b['lines']:
            line_text = "".join([span['text'] for span in line['spans']]).replace('\u200b', '').strip()
            if line_text:
                text_parts.append(line_text)
        
        block_text = " ".join(text_parts).strip()
        if not block_text:
            continue
            
        spans = [s for l in b['lines'] for s in l['spans']]
        font_size = spans[0]['size'] if spans else 10
        is_bold = any(s['flags'] & 2 for s in spans)
        
        # Header Detection
        header_keywords = ["Agenda", "Meeting", "Minutes", "Report"]
        is_keyword_header = any(k in block_text for k in header_keywords) and len(block_text) < 60
        
        if (font_size > 14 or (is_keyword_header and font_size > 11)) and not is_footer and not is_header_area:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            
            rst_lines.append("\n" + block_text)
            if font_size > 14:
                rst_lines.append("=" * len(block_text))
            else:
                rst_lines.append("-" * len(block_text))
            continue

        # Split block if it contains multiple list items
        # Now \u200b is removed, the regex should work perfectly
        sub_items = re.split(r'(\s[a-z]\.\s|\s\d+\.\s|\s[ivx]+\.\s)', " " + block_text)
        if len(sub_items) > 1:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            
            current_item = sub_items[0].strip()
            for j in range(1, len(sub_items), 2):
                if current_item:
                    indent = get_list_indent(current_item) or ""
                    rst_lines.append(f"{indent}{current_item}")
                current_item = (sub_items[j] + sub_items[j+1]).strip()
            
            if current_item:
                indent = get_list_indent(current_item) or ""
                rst_lines.append(f"{indent}{current_item}")
            continue

        # Nested List Logic
        indent = get_list_indent(block_text)
        if indent is not None:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            rst_lines.append(f"\n{indent}{block_text}")
            continue

        # Line Block Logic (Short lines in header/footer)
        if is_footer or is_header_area:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            rst_lines.append(f"| {block_text}")
            continue

        # Regular Paragraph Merging
        # We rely mostly on PyMuPDF's block grouping. If blocks are separate, we assume they are separate paragraphs unless they look very suspiciously like continuations.
        if current_paragraph:
            prev_text = current_paragraph[-1]
            # Simple check: If previous text didn't end with punctuation and current starts with lowercase, merge.
            if not prev_text.endswith(('.', ':', '!', '?')) and block_text[0].islower():
                current_paragraph.append(block_text)
            else:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = [block_text]
        else:
            current_paragraph.append(block_text)

    if current_paragraph:
        rst_lines.append(" ".join(current_paragraph))

    return "\n\n".join(rst_lines)

def extract_premium_text(pdf_path):
    doc = fitz.open(pdf_path)
    full_rst = []
    num_pages = len(doc)

    for i, page in enumerate(doc):
        blocks_data = page.get_text("dict")["blocks"]
        content_blocks = []
        footer_blocks = []
        header_blocks = []
        
        page_height = page.rect.height
        HEADER_MARGIN = 110
        FOOTER_MARGIN = 105

        for b in blocks_data:
            if b['type'] != 0: continue
            
            y0, y1 = b['bbox'][1], b['bbox'][3]
            block_text = " ".join([" ".join([s['text'] for s in l['spans']]) for l in b['lines']]).strip()
            
            if i == 0:
                if y0 > (page_height - FOOTER_MARGIN): continue
                if y1 < HEADER_MARGIN:
                    header_blocks.append(b)
                else:
                    content_blocks.append(b)
            elif i == num_pages - 1:
                if y1 < HEADER_MARGIN: continue
                if y0 > (page_height - FOOTER_MARGIN) or any(s in block_text for s in SOCIETY_STRINGS):
                    footer_blocks.append(b)
                else:
                    content_blocks.append(b)
            else:
                if y1 < HEADER_MARGIN or y0 > (page_height - FOOTER_MARGIN): continue
                if any(s in block_text for s in SOCIETY_STRINGS) and len(block_text) < 200: continue
                content_blocks.append(b)
        
        if i == 0 and header_blocks:
            full_rst.append(format_as_rst(header_blocks, is_header_area=True))
            full_rst.append("\n----\n")
            
        page_rst = format_as_rst(content_blocks)
        # Clean up excessive newlines caused by line blocks
        page_rst = re.sub(r'\|\s+([^\n]+)\n\n\|\s+([^\n]+)', r'| \1\n| \2', page_rst)
        full_rst.append(page_rst)
        
        if i < num_pages - 1:
            full_rst.append("\n----\n")
        else:
            if footer_blocks:
                full_rst.append("\n----\n")
                footer_rst = format_as_rst(footer_blocks, is_footer=True)
                footer_rst = re.sub(r'\|\s+([^\n]+)\n\n\|\s+([^\n]+)', r'| \1\n| \2', footer_rst)
                full_rst.append(footer_rst)
    
    return "\n\n".join(full_rst)

def ingest_pdf(pdf_path, category, original_lang='en', title=None, description=None, publish=False):
    pdf_path = Path(pdf_path)
    if not pdf_path.exists(): return

    if not title: title = pdf_path.stem.replace("-", " ").replace("_", " ").title()
    
    file_stem = pdf_path.stem
    target_dir = Path(f"docs/source/{category}")
    target_dir.mkdir(parents=True, exist_ok=True)
    rst_path = target_dir / f"{file_stem}.rst"

    print(f"Extracting premium text from {pdf_path}...")
    text = extract_premium_text(pdf_path)

    print(f"Archiving to Zenodo (Publish={publish})...")
    creators = [{'name': 'KNA-RNAS Society', 'affiliation': 'KNA-RNAS'}]
    doi_or_id = archive_document(str(pdf_path), title, description or f"Official {category} document", creators, publish=publish)
    
    doi_display = f":doi:`{doi_or_id}`" if publish and not isinstance(doi_or_id, int) else f"Draft ID: {doi_or_id}"

    downloads_dir = Path("docs/source/_static/downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target_pdf_abs = Path("docs/source/_static/downloads") / pdf_path.name
    shutil.copy(pdf_path, target_pdf_abs)

    rel_path_to_static = "../" * len(category.split('/')) + "_static/downloads/" + pdf_path.name

    rst_content = f"""{title}
{"=" * len(title)}

.. document-of-record::
   :original-lang: {original_lang}

.. note::

   - **Archived DOI**: {doi_display}
   - **Original Document**: :download:`Download PDF <{rel_path_to_static}>`

{text}

.. document-status::
   :approved: true
   :approved_in: Automated Ingestion
"""

    with open(rst_path, "w") as f: f.write(rst_content)
    print(f"Created RST file at {rst_path}")

    print("\nRunning translation update...")
    try:
        subprocess.run(["make", "gettext"], cwd="docs", check=True)
        subprocess.run(["sphinx-intl", "update", "-p", "build/gettext", "-l", "nl"], cwd="docs", check=True)
        subprocess.run(["python3", "scripts/translate_docs.py"], check=True)
    except Exception as e: print(f"Translation failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--category", default="minutes")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--title")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    ingest_pdf(args.pdf_path, args.category, args.lang, args.title, publish=args.publish)
