import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import deepl
import polib

# Load environment variables
load_dotenv()

API_KEY = os.getenv("DEEPL_API_KEY")
if not API_KEY or API_KEY == "your_deepl_api_key_here":
    print("Error: DEEPL_API_KEY is not set or is using the template value. Please update your .env file.")
    sys.exit(1)

try:
    translator = deepl.Translator(API_KEY)
except deepl.DeepLException as e:
    print(f"Failed to initialize DeepL Translator: {e}")
    sys.exit(1)

# Path to the Dutch locale messages
LOCALE_DIR = Path(__file__).resolve().parent.parent / "docs" / "locale" / "nl" / "LC_MESSAGES"

if not LOCALE_DIR.exists():
    print(f"Warning: Locale directory not found at {LOCALE_DIR}. You may need to run `make gettext` and `sphinx-intl update -p build/gettext -l nl` first.")
    sys.exit(0)

# Traverse all .po files
po_files = list(LOCALE_DIR.rglob("*.po"))
if not po_files:
    print(f"No .po files found in {LOCALE_DIR}.")
    sys.exit(0)

total_translated = 0

print(f"Scanning for missing translations in {LOCALE_DIR}...")

for po_file in po_files:
    po = polib.pofile(str(po_file))
    
    modified = False
    # We include untranslated entries and all fuzzy entries (which Sphinx ignores)
    to_translate = [e for e in po if not e.msgstr or e.fuzzy]
    
    if not to_translate:
        continue
        
    print(f"\nProcessing {po_file.name} ({len(to_translate)} entries to translate)...")
    
    for entry in to_translate:
        if not entry.msgid.strip():
            continue
            
        try:
            # We preserve formatting to ensure rST syntax doesn't get completely mangled
            result = translator.translate_text(
                entry.msgid, 
                source_lang="EN", 
                target_lang="NL",
                preserve_formatting=True
            )
            entry.msgstr = result.text
            entry.fuzzy = False
            modified = True
            total_translated += 1
            print(f"  ✓ {entry.msgid[:40].replace(chr(10), ' ')}... -> {entry.msgstr[:40].replace(chr(10), ' ')}...")
        except deepl.DeepLException as e:
            print(f"  ❌ DeepL Error on '{entry.msgid[:30]}...': {e}")
    
    if modified:
        po.save()
        print(f"Saved updates to {po_file.name}")

print(f"\n✅ Done! Translated {total_translated} new strings.")
