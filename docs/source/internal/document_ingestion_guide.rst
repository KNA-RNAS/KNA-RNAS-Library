Document Ingestion Guide
========================

This guide describes the process for adding new official documents (PDFs) to the KNA-RNAS Library. The system is designed to automate text extraction, RST generation, translation updates, and Zenodo archiving.

Prerequisites
-------------

Before ingesting a document, ensure you have:

1.  **Python 3.10+** installed with a configured virtual environment.
2.  **Required Packages**: Install dependencies via ``pip install -r requirements.txt`` (primarily ``pymupdf``, ``requests``, and ``python-dotenv``).
3.  **Zenodo Access**: A valid ``ZENODO_ACCESS_TOKEN`` in your ``.env`` file.
4.  **PDF Metadata**: The document category, title, and original language.

Directory Structure
-------------------

Documents are organized into the following categories in ``docs/source/``:

*   ``communication/``: Official announcements and letters.
*   ``governing-docs/``: Statutes, bylaws, and official registrations.
*   ``historical-docs/``: Significant archival materials.
*   ``minutes/``: Records of board and general meetings.
*   ``publications/``: Newsletters and proceedings.

Ingestion Workflow
------------------

Step 1: Prepare the PDF
~~~~~~~~~~~~~~~~~~~~~~~

Ensure the PDF is clearly legible. The ingestion script uses semantic analysis to strip headers/footers and identify society-specific strings (e.g., "Royal Netherlands Astronomical Society").

Step 2: Run the Ingestion Script
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the ``scripts/ingest_document.py`` tool to process the file.

.. code-block:: bash

   python3 scripts/ingest_document.py path/to/your/document.pdf --category <category> --title "Official Document Title"

**Arguments:**

*   ``pdf_path``: Path to the source PDF file.
*   ``--category``: One of the folders listed above (default: ``minutes``).
*   ``--title``: The display title for the library.
*   ``--lang``: Original language code (default: ``en``).
*   ``--publish``: (Optional) If included, immediately publishes to Zenodo (PRODUCTION). **Omit this to create a draft.**

Step 3: Review Generated Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The script performs the following actions:

1.  **Text Extraction**: Converts PDF content to premium reStructuredText.
2.  **Static Copy**: Copies the PDF to ``docs/source/_static/archive/``.
3.  **RST Creation**: Generates the ``.rst`` file in the specified category folder.
4.  **Zenodo Archiving**: Creates a **Draft Deposition** on Zenodo.
5.  **Translation Update**: Runs ``make gettext`` and updates Dutch translations via ``scripts/translate_docs.py``.

Step 4: Review Zenodo Draft
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Visit your Zenodo dashboard to review the draft entry.

**Zenodo Metadata Draft Details:**

*   **Upload Type**: Publication
*   **Publication Type**: Report
*   **Access Right**: Open Access
*   **License**: Creative Commons Attribution 4.0 International (CC-BY-4.0)
*   **Communities**: ``kna-rnas``

Once reviewed, you can manually publish on Zenodo to receive a permanent DOI, then update the ``:doi:`` field in the generated RST file if necessary.

Step 5: Verify and Commit
~~~~~~~~~~~~~~~~~~~~~~~~~

Build the documentation locally to ensure everything looks correct:

.. code-block:: bash

   cd docs
   make html

If satisfied, commit the new files and create a Pull Request.

Troubleshooting
---------------

*   **Extraction Errors**: If the PDF layout is complex, the script might misidentify headers. Manually edit the generated ``.rst`` file to fix structural issues.
*   **Translation Failures**: Ensure ``sphinx-intl`` is installed and configured correctly.
*   **Zenodo Timeout**: If the upload fails, check your internet connection and verify the ``ZENODO_ACCESS_TOKEN`` permissions.
