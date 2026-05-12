import subprocess
from pathlib import Path

doc_path = Path("/home/jake/Downloads/Minutes RNAS Meeting 2025.docx")
result = subprocess.run(
    ["pandoc", str(doc_path), "--from", "docx", "--to", "rst", "--wrap=none"],
    capture_output=True, text=True, check=True
)
print("--- START RAW PANDOC ---")
print(result.stdout[:2000]) # First 2000 chars
print("--- END RAW PANDOC ---")
