"""Upload enriched FHIR bundles to a FHIR server using individual POSTs.

Synthea transaction bundles are often rejected by public HAPI FHIR servers
due to strict reference validation or size limits. This script extracts the
resources we need, POSTs the Patient first to get a real server ID, then
updates all Observation/Condition/Encounter resources to point to that ID
before POSTing them.

Default target: https://hapi.fhir.org/baseR4 (public HAPI FHIR R4 test server).
"""

import json
import sys
import time
from pathlib import Path

import httpx

BUNDLE_DIR = Path(__file__).resolve().parent.parent / "demo_data" / "fhir_bundles"
DEFAULT_SERVER = "https://hapi.fhir.org/baseR4"


def _clean_resource_references(res: dict, new_patient_ref: str) -> dict:
    """Strip complex references and set the subject/patient reference."""
    # Force subject/patient reference to our new ID
    if res["resourceType"] == "Encounter":
        res["subject"] = {"reference": new_patient_ref}
        res.pop("serviceProvider", None)
        res.pop("participant", None)
        res.pop("location", None)
    else:
        res["subject"] = {"reference": new_patient_ref}
        res.pop("encounter", None)
        res.pop("performer", None)
        res.pop("asserter", None)
    
    return res


def upload_single_resource(client: httpx.Client, rt: str, res: dict) -> dict:
    """POST a single resource."""
    resp = client.post(f"/{rt}", json=res)
    resp.raise_for_status()
    return resp.json()


def main():
    dry_run = "--dry-run" in sys.argv
    server = DEFAULT_SERVER

    for arg in sys.argv[1:]:
        if arg.startswith("--server="):
            server = arg.split("=", 1)[1]

    files = sorted(BUNDLE_DIR.glob("patient_*.json"))
    if not files:
        print(f"No patient bundles found in {BUNDLE_DIR}")
        return

    print(f"{'[DRY RUN] ' if dry_run else ''}Uploading {len(files)} patients context to {server}")
    print()

    success = 0
    failed = 0

    with httpx.Client(base_url=server, headers={"Content-Type": "application/fhir+json"}, timeout=60.0) as client:
        for i, fpath in enumerate(files, 1):
            with open(fpath) as f:
                bundle = json.load(f)

            # Find Patient
            patient_res = None
            for e in bundle.get("entry", []):
                r = e.get("resource", {})
                if r.get("resourceType") == "Patient":
                    patient_res = dict(r)
                    patient_res.pop("generalPractitioner", None)
                    patient_res.pop("managingOrganization", None)
                    break
                    
            if not patient_res:
                print(f"  [{i:02d}/{len(files)}] {fpath.name} FAILED: No patient resource")
                failed += 1
                continue

            # Extract name
            names = patient_res.get("name", [{}])
            patient_name = "unknown"
            if names:
                given = names[0].get("given", [""])[0]
                family = names[0].get("family", "")
                patient_name = f"{given} {family}".strip()

            if dry_run:
                print(f"  [{i:02d}/{len(files)}] {patient_name} - VALIDATED")
                success += 1
                continue

            try:
                # 1. Post Patient
                p_out = upload_single_resource(client, "Patient", patient_res)
                p_id = p_out["id"]
                new_ref = f"Patient/{p_id}"
                
                # 2. Extract and post other resources
                resources_created = 1
                for e in bundle.get("entry", []):
                    r = e.get("resource", {})
                    rt = r.get("resourceType")
                    
                    keep = False
                    if rt == "Condition":
                        keep = True
                    elif rt == "Observation":
                        # Only keep SDOH observations (category: social-history)
                        categories = r.get("category", [])
                        for cat in categories:
                            for coding in cat.get("coding", []):
                                if coding.get("code") == "social-history":
                                    keep = True
                    elif rt == "Encounter":
                        keep = True
                        
                    if keep:
                        cleaned = _clean_resource_references(dict(r), new_ref)
                        upload_single_resource(client, rt, cleaned)
                        resources_created += 1

                print(f"  [{i:02d}/{len(files)}] {patient_name} -> {resources_created} resources created (ID: {p_id})")
                success += 1
                time.sleep(0.5)

            except httpx.HTTPStatusError as exc:
                print(f"  [{i:02d}/{len(files)}] {patient_name} FAILED: {exc.response.status_code}")
                try:
                    print(f"    Reason: {json.dumps(exc.response.json(), indent=2)}")
                except:
                    pass
                failed += 1
            except Exception as exc:
                print(f"  [{i:02d}/{len(files)}] {patient_name} FAILED: {exc}")
                failed += 1

    print()
    print(f"Done. {success} succeeded, {failed} failed.")
    if not dry_run:
        print(f"Verify at: {server}/Patient?_tag=https://sdoh-demo|sdoh-project&_count=5")


if __name__ == "__main__":
    main()
