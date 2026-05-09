import os
import sys
import argparse
from pathlib import Path
import fitz  # PyMuPDF
from archive_to_zenodo import archive_document
import subprocess
import shutil

# Common Society Headers/Footers to potentially strip
SOCIETY_STRINGS = [
    "Royal Netherlands Astronomical Society",
    "Koninklijke Nederlandse Astronomenclub",
    "Office of the Secretary",
    "Het Kantoor van de Secretaris",
    "Executive Committee of the Board",
    "KvK: 40047819",
    "www.kna-rnas.nl"
]

def clean_text_block(text):
    """Basic cleaning of text blocks."""
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip common society headers if they appear alone
        if any(s in line for s in SOCIETY_STRINGS) and len(line) < 100:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def extract_structured_text(pdf_path):
    """Extract text using PyMuPDF with header/footer stripping."""
    doc = fitz.open(pdf_path)
    full_text = []
    num_pages = len(doc)

    for i, page in enumerate(doc):
        # Extract blocks to maintain some structure
        blocks = page.get_text("blocks")
        page_text = []
        
        for b in blocks:
            block_text = b[4].strip()
            if not block_text:
                continue
            
            # Header Stripping: Strip society strings from all pages except the first
            if i > 0:
                if any(s in block_text for s in SOCIETY_STRINGS) and len(block_text) < 200:
                    continue
            
            # Footer Stripping: Strip society strings from all pages except the last
            if i < num_pages - 1:
                # Often footers are at the bottom of the page (check block y-coordinate)
                # block b is (x0, y0, x1, y1, text, block_no, block_type)
                if b[1] > page.rect.height * 0.8:
                     if any(s in block_text for s in SOCIETY_STRINGS):
                         continue

            page_text.append(block_text)
        
        full_text.append("\n\n".join(page_text))
    
    return "\n\n".join(full_text)

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
    # Use category/filename structure
    target_dir = Path(f"docs/source/{category}")
    target_dir.mkdir(parents=True, exist_ok=True)
    rst_path = target_dir / f"{file_stem}.rst"

    # 1. Extract Text
    print(f"Extracting structured text from {pdf_path}...")
    text = extract_structured_text(pdf_path)

    # 2. Upload to Zenodo
    print(f"Archiving to Zenodo (Publish={publish})...")
    if not description:
        description = f"Official {category} document: {title}"
    
    creators = [{'name': 'KNA-RNAS Society', 'affiliation': 'KNA-RNAS'}]
    
    # archive_document now handles the publish flag
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
    # We use a path relative to the RST file for the download link
    # Since rst is in docs/source/{category}/, we need to go up one level to reach _static
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

    with open(rst_path, "w") as f:
        f.write(rst_content)
    
    print(f"Created RST file at {rst_path}")

    # 5. Open for Manual Polish (Optional but recommended)
    print(f"\n--- ACTION REQUIRED ---")
    print(f"Please review and polish the formatting at: {rst_path}")
    print(f"Once you are happy, commit the changes.")

    # 6. Run Translation
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
