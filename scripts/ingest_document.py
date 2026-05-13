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

def slugify(text):
    """Converts a string to a lowercase-kebab-case slug."""
    path = Path(text)
    stem = path.stem
    stem = stem.lower()
    stem = re.sub(r'[^a-z0-9]+', '-', stem)
    return stem.strip('-')

def clean_rst(text):
    """Post-processes Pandoc RST to fix split list items and formatting issues."""
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if not cleaned_lines:
            cleaned_lines.append(line)
            continue
        
        # If current line starts with space(s) and isn't a new list marker
        if re.match(r'^\s+\S', line) and not re.match(r'^\s*[\-\*\d\.]+\s', line):
            # Look back for the last non-empty line to see if we should join
            idx = len(cleaned_lines) - 1
            while idx >= 0 and not cleaned_lines[idx].strip():
                idx -= 1
            
            if idx >= 0:
                last_non_empty = cleaned_lines[idx]
                # Join if the last line doesn't end with terminal punctuation
                if not last_non_empty.strip().endswith(('.', ':', '!', '?', '"')):
                    cleaned_lines[idx] = last_non_empty.rstrip('\\ ').rstrip() + " " + line.lstrip()
                    continue

        cleaned_lines.append(line)
            
    return '\n'.join(cleaned_lines)

def extract_structural_text(doc_path, media_dir=None):
    """Uses Pandoc to extract structural RST from Word/ODT files."""
    print(f"Extracting structural text from {doc_path} using Pandoc...")
    try:
        # Convert to rst
        # Using --wrap=none to ensure long lines (especially links) are not split
        cmd = ["pandoc", str(doc_path), "--from", "docx" if doc_path.suffix == ".docx" else "odt", "--to", "rst", "--wrap=none"]
        if media_dir:
            media_dir.mkdir(parents=True, exist_ok=True)
            cmd.append(f"--extract-media={media_dir}")

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, check=True
        )
        text = result.stdout
        
        # Post-process Pandoc output for our specific needs
        text = clean_rst(text)

        # Fix image paths if media was extracted
        if media_dir:
            # Pandoc output often contains the full path to the extracted media.
            # We want to convert this to a Sphinx-relative path starting with /
            # Sphinx considers / to be the root of the source directory (docs/source).
            text = re.sub(r'image:: \.?docs/source', 'image:: ', text)
            
            # Fix attributes on the same line (Pandoc sometimes puts these on one line)
            # Sphinx requires them on new lines with indentation.
            text = re.sub(r'image:: ([^\s]+) :width: ([^\s]+) :height: ([^\s]+)', r'image:: \1\n   :width: \2\n   :height: \3', text)
            # Also handle single attributes just in case
            text = re.sub(r'image:: ([^\s]+) :width: ([^\s]+)(?!\s+:height:)', r'image:: \1\n   :width: \2', text)
            text = re.sub(r'image:: ([^\s]+) :height: ([^\s]+)', r'image:: \1\n   :height: \2', text)
            
        return text
    except Exception as e:
        print(f"Pandoc conversion failed: {e}")
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

def ingest_document(file_path, category, original_lang='en', title=None, description=None, publish=False, deposition_id=None, pdf_path=None):
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"Error: File not found {file_path}")
        return

    if not title: title = file_path.stem.replace("-", " ").replace("_", " ").title()
    
    file_stem = slugify(title)
    target_dir = Path(f"docs/source/{category}")
    target_dir.mkdir(parents=True, exist_ok=True)
    rst_path = target_dir / f"{file_stem}.rst"

    # 1. Determine Source & Extract Text
    if file_path.suffix.lower() in ['.docx', '.odt']:
        media_dir = Path(f"docs/source/_static/images/{file_stem}")
        text = extract_structural_text(file_path, media_dir=media_dir)
        if pdf_path:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                print(f"Error: Provided PDF path does not exist: {pdf_path}.")
                return
        else:
            print("Error: No PDF provided. You must provide a PDF using --pdf.")
            return
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
    # Ensure standard filename in archive
    target_pdf_name = f"{file_stem}.pdf"
    target_pdf_abs = (downloads_dir / target_pdf_name).resolve()
    if pdf_path.resolve() != target_pdf_abs:
        shutil.copy(pdf_path, target_pdf_abs)

    rel_path_to_static = "../" * len(category.split('/')) + "_static/archive/" + target_pdf_name

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
   :approved: false
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
    parser.add_argument("--pdf", help="Path to the original PDF (document of record)")
    args = parser.parse_args()
    ingest_document(args.file_path, args.category, args.lang, args.title, publish=args.publish, deposition_id=args.deposition_id, pdf_path=args.pdf)
