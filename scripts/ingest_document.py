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

def is_list_item(text):
    """Detect if a line looks like a list item."""
    patterns = [
        r'^\d+\.',         # 1.
        r'^[a-z]\.',       # a.
        r'^[ivx]+\.',      # i., ii.
        r'^[\*\-\+]\s',    # * , - 
    ]
    return any(re.match(p, text.strip().lower()) for p in patterns)

def format_as_rst(blocks, page_height):
    """Convert extracted blocks into well-formatted RST."""
    rst_lines = []
    
    # Sort blocks by y-coordinate then x-coordinate
    blocks.sort(key=lambda b: (round(b['bbox'][1]), round(b['bbox'][0])))
    
    current_paragraph = []
    
    for i, b in enumerate(blocks):
        text = ""
        for line in b['lines']:
            for span in line['spans']:
                text += span['text']
        
        text = text.strip()
        if not text:
            continue
            
        # Detect if this block is a header
        is_header = False
        spans = [s for l in b['lines'] for s in l['spans']]
        if not spans: continue
        
        font_size = spans[0]['size']
        if font_size > 11.5: 
            is_header = True

        if is_header and len(text) < 100:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            rst_lines.append("\n" + text)
            if font_size > 14:
                rst_lines.append("-" * len(text))
            else:
                rst_lines.append("~" * len(text))
            continue

        # Detect footer-like strings to keep them separate
        is_society_branding = any(s in text for s in SOCIETY_STRINGS)

        if is_list_item(text) or is_society_branding:
            if current_paragraph:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = []
            rst_lines.append("\n" + text)
            continue

        # Merge with current paragraph if y-distance is small
        if current_paragraph:
            prev_b = blocks[i-1]
            dist = b['bbox'][1] - prev_b['bbox'][3]
            if dist < 12 and not is_list_item(text):
                current_paragraph.append(text)
            else:
                rst_lines.append(" ".join(current_paragraph))
                current_paragraph = [text]
        else:
            current_paragraph.append(text)

    if current_paragraph:
        rst_lines.append(" ".join(current_paragraph))

    return "\n\n".join(rst_lines)

def extract_premium_text(pdf_path):
    """Extract text with geometric header/footer stripping and layout reconstruction."""
    doc = fitz.open(pdf_path)
    full_rst = []
    num_pages = len(doc)

    for i, page in enumerate(doc):
        # Extract blocks with detail
        blocks_data = page.get_text("dict")["blocks"]
        clean_blocks = []
        
        page_height = page.rect.height
        
        # Aggressive Header/Footer Margins
        HEADER_MARGIN = 110
        FOOTER_MARGIN = 100

        for b in blocks_data:
            if b['type'] != 0: # 0 is text
                continue
            
            y0 = b['bbox'][1]
            y1 = b['bbox'][3]
            
            # Geometry-based Stripping
            if i == 0:
                if y0 > (page_height - FOOTER_MARGIN):
                    continue
            elif i == num_pages - 1:
                if y1 < HEADER_MARGIN:
                    continue
            else:
                if y1 < HEADER_MARGIN or y0 > (page_height - FOOTER_MARGIN):
                    continue
            
            # Content-based backup stripping
            block_text = "".join(["".join([s['text'] for s in l['spans']]) for l in b['lines']])
            if any(s in block_text for s in SOCIETY_STRINGS) and len(block_text) < 250:
                # Keep on page 1 header / last page footer ONLY if in margins
                if i == 0 and y1 < HEADER_MARGIN:
                    pass
                elif i == num_pages -1 and y0 > (page_height - FOOTER_MARGIN):
                    pass
                else:
                    continue

            clean_blocks.append(b)
        
        full_rst.append(format_as_rst(clean_blocks, page_height))
        
        if i < num_pages - 1:
            full_rst.append("\n.. raw:: html\n\n   <hr class=\"gold-line\">\n")
    
    return "\n\n".join(full_rst)

def ingest_pdf(pdf_path, category, original_lang='en', title=None, description=None, publish=False):
    """
    Automated workflow to ingest a PDF into the KNA-RNAS library.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: File {pdf_path} not found.")
        return

    if not title:
        title = pdf_path.stem.replace("-", " ").replace("_", " ").title()
    
    file_stem = pdf_path.stem
    target_dir = Path(f"docs/source/{category}")
    target_dir.mkdir(parents=True, exist_ok=True)
    rst_path = target_dir / f"{file_stem}.rst"

    # 1. Extract Text
    print(f"Extracting premium text from {pdf_path}...")
    text = extract_premium_text(pdf_path)

    # 2. Upload to Zenodo
    print(f"Archiving to Zenodo (Publish={publish})...")
    if not description:
        description = f"Official {category} document: {title}"
    
    creators = [{'name': 'KNA-RNAS Society', 'affiliation': 'KNA-RNAS'}]
    doi_or_id = archive_document(str(pdf_path), title, description, creators, publish=publish)
    
    doi_display = "PENDING (Draft Mode)"
    if doi_or_id:
        if isinstance(doi_or_id, int) or "TEST" in str(doi_or_id):
            doi_display = f"Draft Deposition ID: {doi_or_id}"
        else:
            doi_display = f":doi:`{doi_or_id}`"

    # 3. Handle PDF Download
    downloads_dir = Path("docs/source/_static/downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target_pdf_rel = Path(f"_static/downloads/{pdf_path.name}")
    target_pdf_abs = Path("docs/source") / target_pdf_rel
    shutil.copy(pdf_path, target_pdf_abs)

    # 4. Create RST Content
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

.. raw:: html

   <hr class="gold-line">

.. document-status::
   :approved: true
   :approved_in: Automated Ingestion
"""

    with open(rst_path, "w") as f:
        f.write(rst_content)
    
    print(f"Created RST file at {rst_path}")

    # 5. Run Translation
    print("\nRunning translation update...")
    try:
        subprocess.run(["make", "gettext"], cwd="docs", check=True)
        subprocess.run(["sphinx-intl", "update", "-p", "build/gettext", "-l", "nl"], cwd="docs", check=True)
        subprocess.run(["python3", "scripts/translate_docs.py"], check=True)
    except Exception as e:
        print(f"Translation failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a PDF into the KNA-RNAS Library.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--category", default="minutes", help="Category folder")
    parser.add_argument("--lang", default="en", help="Original language")
    parser.add_argument("--title", help="Document title")
    parser.add_argument("--publish", action="store_true", help="Publish to Zenodo immediately")
    
    args = parser.parse_args()
    ingest_pdf(args.pdf_path, args.category, args.lang, args.title, publish=args.publish)
