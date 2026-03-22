import os
import glob
import json
import httpx
import asyncio
from config import get_settings

SYNTHEA_OUTPUT_DIR = "../synthea/output/fhir" 

async def upload_bundle(client: httpx.AsyncClient, file_path: str, fhir_base_url: str):
    """Reads a single Synthea JSON bundle and POSTs it to the FHIR server."""
    with open(file_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    try:
        response = await client.post(
            fhir_base_url, 
            json=bundle, 
            headers={"Content-Type": "application/fhir+json"}
        )
        response.raise_for_status()
        print(f"Successfully uploaded: {os.path.basename(file_path)}")
    except httpx.HTTPStatusError as e:
        print(f"Failed to upload {os.path.basename(file_path)}: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"Error uploading {os.path.basename(file_path)}: {str(e)}")

async def main():
    settings = get_settings()
    fhir_base_url = settings.fhir_base_url.rstrip("/") 
    
    search_pattern = os.path.join(SYNTHEA_OUTPUT_DIR, "*.json")
    files = glob.glob(search_pattern)
    
    patient_files = [f for f in files if "hospitalInformation" not in f and "practitionerInformation" not in f]
    
    if not patient_files:
        print(f"No patient JSON files found in {SYNTHEA_OUTPUT_DIR}. Did you run Synthea?")
        return

    print(f"Found {len(patient_files)} patient records. Uploading to {fhir_base_url}...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [upload_bundle(client, file_path, fhir_base_url) for file_path in patient_files]
        await asyncio.gather(*tasks)
        
    print("Upload process complete!")

if __name__ == "__main__":
    asyncio.run(main())