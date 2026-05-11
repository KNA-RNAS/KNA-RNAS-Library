import os
import requests
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

ACCESS_TOKEN = os.getenv("ZENODO_ACCESS_TOKEN")
BASE_URL = "https://zenodo.org/api"

def list_depositions():
    """List all depositions for the user."""
    url = f"{BASE_URL}/deposit/depositions"
    params = {'access_token': ACCESS_TOKEN, 'size': 100}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Error listing depositions: {response.status_code}")
        return []
    return response.json()

def delete_drafts(all=False):
    """Delete draft depositions."""
    depositions = list_depositions()
    deleted_count = 0
    
    print(f"Found {len(depositions)} depositions.")
    
    for dep in depositions:
        # Check if it's a draft (submitted is False)
        if not dep.get('submitted', False) or all:
            dep_id = dep['id']
            title = dep.get('title', 'No Title')
            print(f"Deleting draft '{title}' (ID: {dep_id})...")
            
            url = f"{BASE_URL}/deposit/depositions/{dep_id}"
            params = {'access_token': ACCESS_TOKEN}
            del_resp = requests.delete(url, params=params)
            
            if del_resp.status_code == 204:
                deleted_count += 1
            else:
                print(f"Failed to delete {dep_id}: {del_resp.status_code}")
    
    print(f"\nSuccessfully deleted {deleted_count} drafts.")

if __name__ == "__main__":
    if not ACCESS_TOKEN:
        print("Error: ZENODO_ACCESS_TOKEN not found in .env")
        exit(1)
        
    parser = argparse.ArgumentParser(description="Cleanup Zenodo draft depositions.")
    parser.add_argument("--all", action="store_true", help="Force delete ALL depositions (caution!)")
    args = parser.parse_args()
    
    confirm = input("This will delete ALL DRAFT depositions on your Zenodo account. Are you sure? (y/N): ")
    if confirm.lower() == 'y':
        delete_drafts(all=args.all)
    else:
        print("Aborted.")
