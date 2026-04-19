import os
import json
import glob
import httpx
from dotenv import load_dotenv

def main():
    load_dotenv()
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    
    if not (tenant_id and client_id and client_secret):
        print("Error: AZURE_TENANT_ID, AZURE_CLIENT_ID, or AZURE_CLIENT_SECRET not found in .env")
        return

    base_url = os.getenv("FHIR_BASE_URL", "https://socialrisk-server.fhir.azurehealthcareapis.com")
    print(f"Targeting FHIR Server: {base_url}")
    print("Fetching dynamic OAuth2 token...")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_resp = httpx.post(token_url, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": f"{base_url}/.default"
    }, timeout=10.0)
    
    try:
        token_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"Authentication failed: {exc.response.text}")
        return
        
    token = token_resp.json()["access_token"]
    print("Successfully fetched token.")

    client = httpx.Client(
        base_url=base_url,
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
    )

    bundle_dir = os.path.join(os.path.dirname(__file__), "..", "synthea_temp", "output", "fhir")
    if not os.path.exists(bundle_dir):
        print(f"Error: Could not find Synthea output directory at {bundle_dir}")
        return

    files = glob.glob(os.path.join(bundle_dir, "*.json"))
    print(f"Found {len(files)} JSON bundles to upload.")

    success_count = 0
    error_count = 0

    # Separate files by type
    hospitals = [f for f in files if os.path.basename(f).startswith("hospital")]
    practitioners = [f for f in files if os.path.basename(f).startswith("practitioner")]
    patients = [f for f in files if not os.path.basename(f).startswith("hospital") and not os.path.basename(f).startswith("practitioner")]

    # Upload Hospitals First
    for filepath in hospitals:
        with open(filepath, "r") as f:
            bundle = json.load(f)
        print(f"Uploading {os.path.basename(filepath)} ...", end=" ", flush=True)
        resp = client.post("/", json=bundle)
        print("OK" if resp.status_code in (200, 201) else f"FAILED ({resp.status_code})")

    # Upload Practitioners Second
    for filepath in practitioners:
        with open(filepath, "r") as f:
            bundle = json.load(f)
        print(f"Uploading {os.path.basename(filepath)} ...", end=" ", flush=True)
        resp = client.post("/", json=bundle)
        print("OK" if resp.status_code in (200, 201) else f"FAILED ({resp.status_code})")

    # Upload Patients (skip if > 500 entries)
    print("Uploading Patients...")
    for filepath in patients:
        if success_count >= 50:
            print("Reached 50 successful patient uploads. Stopping.")
            break
            
        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            bundle = json.load(f)

        if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
            continue

        entries = bundle.get("entry", [])
        if len(entries) >= 500:
            print(f"Skipping {filename}: {len(entries)} entries (exceeds Azure 500 limit).")
            continue

        print(f"Uploading {filename} ({len(entries)} items) ...", end=" ", flush=True)
        try:
            resp = client.post("/", json=bundle)
            if resp.status_code in (200, 201):
                print("OK")
                success_count += 1
            else:
                print(f"FAILED ({resp.status_code})")
                print(resp.text)
                error_count += 1
        except Exception as e:
            print(f"ERROR: {e}")
            error_count += 1

    print(f"Upload complete. Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()
