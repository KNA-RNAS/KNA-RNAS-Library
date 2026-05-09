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
    "www.kna-rnas.nl"
]

def get_list_indent(text):
    text_lower = text.strip().lower()
    if re.match(r'^\d+\.', text_lower): return ""
    if re.match(r'^[ivx]+\.', text_lower): return "      "
    if re.match(r'^[a-z]\.', text_lower): return "   "
    return None

def is_list_item(text):
    return get_list_indent(text) is not None

def extract_premium_text(pdf_path):
    doc = fitz.open(pdf_path)
    all_lines = []
    num_pages = len(doc)

    for i, page in enumerate(doc):
        page_height = page.rect.height
        HEADER_MARGIN = 115
        FOOTER_MARGIN = 105
        
        blocks_data = page.get_text("dict")["blocks"]
        for b in blocks_data:
            if b['type'] != 0: continue
            
            y0, y1 = b['bbox'][1], b['bbox'][3]
            block_text = "".join([s['text'] for l in b['lines'] for s in l['spans']]).replace('\u200b', '').strip()
            
            if not block_text: continue
            is_society = any(s in block_text for s in SOCIETY_STRINGS)
            
            if i == 0:
                if y0 > (page_height - FOOTER_MARGIN): continue
            elif i == num_pages - 1:
                # On the last page, we MUST strip the header if it exists
                if y1 < HEADER_MARGIN or (is_society and y1 < page_height / 2): continue
            else:
                if y1 < HEADER_MARGIN or y0 > (page_height - FOOTER_MARGIN): continue
                if is_society and len(block_text) < 200: continue
                
            for l in b['lines']:
                line_text = "".join([s['text'] for s in l['spans']]).replace('\u200b', '').strip()
                if line_text:
                    all_lines.append(line_text)

    # 1. Fix detached list markers (e.g. "1." on its own line)
    fixed_lines = []
    skip_next = False
    for i, line in enumerate(all_lines):
        if skip_next:
            skip_next = False
            continue
        if re.match(r'^(\d+\.|[a-z]\.|[ivx]+\.)$', line.lower()) and i + 1 < len(all_lines):
            fixed_lines.append(line + " " + all_lines[i+1])
            skip_next = True
        else:
            fixed_lines.append(line)
            
    # 2. Build paragraphs based on semantic rules
    paragraphs = []
    current_para = []
    
    for line in fixed_lines:
        is_list = is_list_item(line)
        is_header = len(line) < 80 and any(k in line for k in ["Agenda", "Annual General Meeting", "Meeting"])
        is_society = any(s in line for s in SOCIETY_STRINGS)
        is_signature = any(k in line for k in ["Respectfully", "Hoogachtend", "secretary@", "On behalf", "Dr."])
        is_date_loc = re.match(r'^\d+\s(?:January|February|March|April|May|June|July|August|September|October|November|December)\s\d{4},', line)
        
        start_new = False
        if not current_para:
            start_new = False
        elif is_list or is_header or is_society or is_signature or is_date_loc:
            start_new = True
        else:
            prev_line = current_para[-1]
            if prev_line.endswith(('.', ':', '!', '?')):
                start_new = True
            elif any(k in prev_line for k in ["Respectfully", "Hoogachtend", "secretary@", "On behalf", "Dr."]):
                start_new = True
            elif re.match(r'^\d+\s(?:January|February|March|April|May|June|July|August|September|October|November|December)\s\d{4},', prev_line):
                start_new = True
                
        if start_new:
            paragraphs.append(" ".join(current_para))
            current_para = [line]
        else:
            current_para.append(line)
            
    if current_para:
        paragraphs.append(" ".join(current_para))
        
    # 3. Format paragraphs into RST
    rst_lines = []
    
    # Find indices for horizontal rules
    first_content_idx = 0
    for i, p in enumerate(paragraphs):
        if not any(s in p for s in SOCIETY_STRINGS):
            first_content_idx = i
            break
            
    last_content_idx = len(paragraphs) - 1
    for i in range(len(paragraphs)-1, -1, -1):
        if not any(s in paragraphs[i] for s in SOCIETY_STRINGS):
            last_content_idx = i
            break

    prev_type = None
    prev_indent = None

    for i, p in enumerate(paragraphs):
        p = p.replace("Agenda(as proposed)", "Agenda (as proposed)")
        
        if i == first_content_idx:
            rst_lines.extend(["", "----", ""])
            prev_type = "hr"
            
        if i == last_content_idx + 1:
            rst_lines.extend(["", "----", ""])
            prev_type = "hr"
            
        is_society = any(s in p for s in SOCIETY_STRINGS)
        if is_society:
            if prev_type and prev_type != "line_block":
                rst_lines.append("")
            rst_lines.append(f"| {p}")
            prev_type = "line_block"
            continue
            
        indent = get_list_indent(p)
        if indent is not None:
            if prev_type != "list" or prev_indent != indent:
                rst_lines.append("")
            rst_lines.append(f"{indent}{p}")
            prev_type = "list"
            prev_indent = indent
            continue
            
        is_header = len(p) < 80 and any(k in p for k in ["Agenda", "Annual General Meeting", "Meeting"])
        if is_header:
            rst_lines.append("")
            if "Agenda" in p:
                rst_lines.append(p)
                rst_lines.append("-" * len(p))
            elif "Annual" in p:
                rst_lines.append(p)
                rst_lines.append("~" * len(p))
            else:
                rst_lines.append(p)
                rst_lines.append("~" * len(p))
            rst_lines.append("")
            prev_type = "header"
            continue
            
        # Address blocks or dates
        if len(p) < 100 and ("April" in p or "May" in p or "Netherlands" in p) and not p.endswith('.'):
            if prev_type:
                rst_lines.append("")
            rst_lines.append(f"{p}")
            prev_type = "paragraph"
            continue
            
        # Short signature lines
        if len(p) < 60 and not p.endswith('.'):
            if prev_type and prev_type != "line_block":
                rst_lines.append("")
            rst_lines.append(f"| {p}")
            prev_type = "line_block"
            continue
            
        # Normal paragraph
        if prev_type:
            rst_lines.append("")
        rst_lines.append(p)
        prev_type = "paragraph"

    final_rst = "\n".join(rst_lines)
    return final_rst.strip()

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

    downloads_dir = Path("docs/source/_static/archive")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target_pdf_abs = Path("docs/source/_static/archive") / pdf_path.name
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

