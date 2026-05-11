import os
import requests
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ACCESS_TOKEN = os.getenv("ZENODO_ACCESS_TOKEN")
BASE_URL = "https://zenodo.org/api" # Use https://sandbox.zenodo.org/api for testing

def create_deposition(metadata):
    """Create a new deposition on Zenodo."""
    url = f"{BASE_URL}/deposit/depositions"
    params = {'access_token': ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, params=params, data=json.dumps(metadata), headers=headers)
    
    if response.status_code != 201:
        print(f"Error creating deposition: {response.status_code}")
        print(response.json())
        return None
    
    return response.json()

def upload_file(deposition_id, file_path):
    """Upload a file to an existing deposition."""
    url = f"{BASE_URL}/deposit/depositions/{deposition_id}/files"
    params = {'access_token': ACCESS_TOKEN}
    
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(url, params=params, files=files)
        
    if response.status_code != 201:
        print(f"Error uploading file: {response.status_code}")
        print(response.json())
        return False
    
    return True

def publish_deposition(deposition_id):
    """Publish the deposition to get a DOI."""
    url = f"{BASE_URL}/deposit/depositions/{deposition_id}/actions/publish"
    params = {'access_token': ACCESS_TOKEN}
    
    response = requests.post(url, params=params)
    
    if response.status_code != 202:
        print(f"Error publishing deposition: {response.status_code}")
        print(response.json())
        return None
    
    return response.json()

def delete_deposition(deposition_id):
    """Delete a deposition."""
    url = f"{BASE_URL}/deposit/depositions/{deposition_id}"
    params = {'access_token': ACCESS_TOKEN}
    response = requests.delete(url, params=params)
    return response.status_code == 204

def archive_document(file_path, title, description, creators, publish=False, deposition_id=None):
    """Full workflow to archive a document."""
    if not ACCESS_TOKEN:
        print("Error: ZENODO_ACCESS_TOKEN not found in .env")
        return None

    dep_id = deposition_id
    if not dep_id:
        metadata = {
            'metadata': {
                'title': title,
                'upload_type': 'publication',
                'publication_type': 'report',
                'description': description,
                'creators': creators,
                'access_right': 'open',
                'license': 'CC-BY-4.0',
                'communities': [{'identifier': 'kna-rnas'}]
            }
        }
        print(f"Creating deposition for '{title}'...")
        deposition = create_deposition(metadata)
        if not deposition:
            return None
        dep_id = deposition['id']
        print(f"Deposition created with ID: {dep_id}")
    else:
        print(f"Updating existing deposition ID: {dep_id}")
        # To update, we should ideally delete existing files if we're replacing them
        # But Zenodo API for draft update is a bit complex. For now we just attempt upload.
    
    print(f"Uploading file '{file_path}'...")
    if not upload_file(dep_id, file_path):
        # If upload fails, maybe the file already exists? 
        # Zenodo requires deleting the file first if it exists.
        return None
    
    if publish:
        print("Publishing deposition (PRODUCTION)...")
        published = publish_deposition(dep_id)
        if not published:
            return None
        print(f"Successfully archived! DOI: {published['doi']}")
        return published['doi']
    else:
        print(f"Deposition {'updated' if deposition_id else 'created'} as DRAFT. Visit Zenodo to review and publish.")
        return dep_id

if __name__ == "__main__":
    # Example usage
    # archive_document(
    #     "docs/source/historical-docs/80-jaar-vrijheid.rst", 
    #     "80 Jaar Vrijheid", 
    #     "Commemoration of the 80th anniversary of freedom.",
    #     [{'name': 'Noel-Storr, Jacob', 'affiliation': 'KNA-RNAS'}]
    # )
    print("Script loaded. Use as a module or uncomment example usage.")
