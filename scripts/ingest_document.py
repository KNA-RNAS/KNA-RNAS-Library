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

# Patterns for list items
LIST_PATTERNS = [
    r'^\d+\.',         # 1.
    r'^[a-z]\.',       # a.
    r'^[ivx]+\.',      # i., ii.
    r'^[\*\-\+]\s',    # * , - 
]

def is_list_item(text):
    """Detect if a line looks like a list item."""
    return any(re.match(p, text.strip().lower()) for p in LIST_PATTERNS)

def format_as_rst(blocks):
    """Convert extracted blocks into well-formatted RST."""
    rst_lines = []
    
    # Sort blocks by y-coordinate then x-coordinate
    blocks.sort(key=lambda b: (round(b['bbox'][1]), round(b['bbox'][0])))
    
    current_paragraph = []
    
    for i, b in enumerate(blocks):
        text_parts = []
        for line in b['lines']:
            line_text = "".join([span['text'] for span in line['spans']]).strip()
            if line_text:
                text_parts.append(line_text)
        
        block_text = " ".join(text_parts).strip()
        if not block_text:
            continue
            
        # Detect if this block is a header
        spans = [s for l in b['lines'] for s in l['spans']]
        font_size = spans[0]['size'] if spans else 10
        is_bold = any(s['flags'] & 2 for s in spans) # flag 2 is bold in MuPDF
        
        # High-priority header keywords
        header_keywords = ["Agenda", "Meeting", "Minutes", "Report"]
        is_keyword_header = any(k in block_text for k in header_keywords) and len(block_text) < 50
        
        is_header = (font_size > 11.8) or (is_bold and len(block_text) < 60) or is_keyword_header

        if is_header:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            
            rst_lines.append("\n" + block_text)
            if font_size > 14:
                rst_lines.append("-" * len(block_text))
            else:
                rst_lines.append("~" * len(block_text))
            continue

        # Split block if it contains multiple list items
        # Sometimes PDF extraction puts "a. Item 1 b. Item 2" in one block
        sub_items = re.split(r'(\s[a-z]\.\s|\s\d+\.\s)', " " + block_text)
        if len(sub_items) > 1:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            
            # Reconstruct items
            current_item = sub_items[0].strip()
            for j in range(1, len(sub_items), 2):
                if current_item: rst_lines.append(current_item)
                current_item = (sub_items[j] + sub_items[j+1]).strip()
            if current_item: rst_lines.append(current_item)
            continue

        if is_list_item(block_text):
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            rst_lines.append(block_text)
            continue

        # Merge logic: Only merge if the previous line doesn't end with a terminal punctuation
        if current_paragraph:
            prev_text = current_paragraph[-1]
            if prev_text.endswith(('.', ':', '!', '?')) or is_list_item(block_text) or block_text[0].isupper():
                # Potential new paragraph
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = [block_text]
            else:
                current_paragraph.append(block_text)
        else:
            current_paragraph.append(block_text)

    if current_paragraph:
        rst_lines.append(" ".join(current_paragraph))

    return "\n\n".join(rst_lines)

def extract_premium_text(pdf_path):
    """Extract text with geometric header/footer stripping and layout reconstruction."""
    doc = fitz.open(pdf_path)
    full_rst = []
    num_pages = len(doc)

    for i, page in enumerate(doc):
        blocks_data = page.get_text("dict")["blocks"]
        content_blocks = []
        footer_blocks = []
        
        page_height = page.rect.height
        HEADER_MARGIN = 110
        FOOTER_MARGIN = 105

        for b in blocks_data:
            if b['type'] != 0: continue
            
            y0, y1 = b['bbox'][1], b['bbox'][3]
            block_text = " ".join([" ".join([s['text'] for s in l['spans']]) for l in b['lines']]).strip()
            
            # Page 1: Keep header, strip footer
            if i == 0:
                if y0 > (page_height - FOOTER_MARGIN): continue
                content_blocks.append(b)
            # Last Page: Strip header, identify footer separately
            elif i == num_pages - 1:
                if y1 < HEADER_MARGIN: continue
                if y0 > (page_height - FOOTER_MARGIN) or any(s in block_text for s in SOCIETY_STRINGS):
                    footer_blocks.append(b)
                else:
                    content_blocks.append(b)
            # Middle Pages: Strip both
            else:
                if y1 < HEADER_MARGIN or y0 > (page_height - FOOTER_MARGIN): continue
                # Also strip if content matches society strings
                if any(s in block_text for s in SOCIETY_STRINGS) and len(block_text) < 200: continue
                content_blocks.append(b)
        
        # Format the main content
        page_rst = format_as_rst(content_blocks)
        full_rst.append(page_rst)
        
        # Page separator
        if i < num_pages - 1:
            full_rst.append("\n.. raw:: html\n\n   <hr class=\"gold-line\">\n")
        else:
            # Last page: Add gold line BEFORE footer
            if footer_blocks:
                full_rst.append("\n.. raw:: html\n\n   <hr class=\"gold-line\">\n")
                full_rst.append(format_as_rst(footer_blocks))
    
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

    # Handle PDF Download
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

.. raw:: html

   <hr class="gold-line">

{text}

.. document-status::
   :approved: true
   :approved_in: Automated Ingestion
"""

    with open(rst_path, "w") as f: f.write(rst_content)
    print(f"Created RST file at {rst_path}")

    # Run Translation
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
