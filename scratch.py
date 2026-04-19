import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("AZURE_API_KEY")
url = "https://socialrisk-server.fhir.azurehealthcareapis.com/Patient"

response = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"})
print("Status:", response.status_code)
print("Response:", response.json() if response.status_code == 200 else response.text)
