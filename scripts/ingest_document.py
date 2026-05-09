import os
import sys
import argparse
from pathlib import Path
from pdfminer.high_level import extract_text
from archive_to_zenodo import archive_document
import subprocess

def ingest_pdf(pdf_path, category, original_lang='en', title=None, description=None):
    """
    Automated workflow to ingest a PDF into the KNA-RNAS library.
    1. Extract text from PDF.
    2. Upload PDF to Zenodo to get DOI.
    3. Create RST file with metadata and extracted text.
    4. Trigger translation.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: File {pdf_path} not found.")
        return

    # 1. Determine Title and Filename
    if not title:
        title = pdf_path.stem.replace("-", " ").replace("_", " ").title()
    
    file_stem = pdf_path.stem
    rst_path = Path(f"docs/source/{category}/{file_stem}.rst")
    rst_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Extract Text
    print(f"Extracting text from {pdf_path}...")
    try:
        text = extract_text(pdf_path)
    except Exception as e:
        print(f"Error extracting text: {e}")
        text = "[Text extraction failed. Please review the original PDF.]"

    # 3. Upload to Zenodo
    print("Archiving to Zenodo...")
    if not description:
        description = f"Official {category} document: {title}"
    
    # Using a placeholder creator if not provided
    creators = [{'name': 'KNA-RNAS Society', 'affiliation': 'KNA-RNAS'}]
    
    # NOTE: This returns a deposition ID or DOI depending on test mode.
    # In production, we'd want the DOI.
    doi_or_id = archive_document(str(pdf_path), title, description, creators)
    
    if not doi_or_id:
        print("Failed to get DOI from Zenodo. Proceeding without DOI link.")
        doi_link = "PENDING"
    else:
        # If it's a numeric ID (test mode), we use a placeholder DOI
        if isinstance(doi_or_id, int):
            doi_link = f"TEST-ID-{doi_or_id}"
        else:
            doi_link = doi_or_id

    # 4. Create RST Content
    # We copy the PDF to a local _static/downloads folder so Sphinx can serve it
    downloads_dir = Path("docs/source/_static/downloads")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = downloads_dir / pdf_path.name
    import shutil
    shutil.copy(pdf_path, target_pdf)

    rst_content = f"""{title}
{"=" * len(title)}

.. document-of-record::
   :original-lang: {original_lang}

.. note::

   This document is archived on Zenodo with DOI: {doi_link}
   
   - **Original Document**: :download:`Download PDF </_static/downloads/{pdf_path.name}>`

Extracted Content
-----------------

{text}

.. document-status::
   :approved: true
   :approved_in: Automated Ingestion
   :notary_stamp: Pending
"""

    with open(rst_path, "w") as f:
        f.write(rst_content)
    
    print(f"Created RST file at {rst_path}")

    # 5. Update parent index/toctree (Basic approach: check if it's in meeting-minutes.rst)
    # This part is complex to automate perfectly without knowing the structure,
    # but we can append to a 'pending' section or just let the user know.
    print(f"Please ensure {rst_path.relative_to('docs/source')} is added to your toctree.")

    # 6. Run Translation
    print("Running translation script...")
    try:
        # We need to run gettext first to pick up the new file
        subprocess.run(["make", "gettext"], cwd="docs", check=True)
        subprocess.run(["sphinx-intl", "update", "-p", "build/gettext", "-l", "nl"], cwd="docs", check=True)
        subprocess.run(["python3", "scripts/translate_docs.py"], check=True)
    except Exception as e:
        print(f"Translation failed: {e}")

    print("\nDone! Document ingested and translation triggered.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a PDF into the KNA-RNAS Library.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--category", default="minutes", help="Category folder (governing-docs, minutes, etc.)")
    parser.add_argument("--lang", default="en", help="Original language (en/nl)")
    parser.add_argument("--title", help="Document title")
    
    args = parser.parse_args()
    ingest_pdf(args.pdf_path, args.category, args.lang, args.title)
