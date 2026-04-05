import pytest
import httpx
from unittest.mock import MagicMock, patch
from services.fhir_client import FHIRClient, FHIRError, FHIRNotFoundError

MOCK_BASE = "https://hapi.fhir.org/baseR4"


@pytest.fixture
def client():
    return FHIRClient(base_url=MOCK_BASE, use_tag_filter=False)


def _mock_bundle(resource_type: str, resources: list) -> dict:
    return {
        "resourceType": "Bundle",
        "entry": [{"resource": {**r, "resourceType": resource_type}} for r in resources],
        "link": [],
    }


@pytest.fixture
def high_risk_patient():
    return {
        "patient_id":   "test-patient-abc123",
        "display_name": "John Test",
        "score":        15,
        "tier":         "HIGH",
        "explanations": ["Housing instability", "Diabetes", "Very high recent ED utilization (≥3 visits)"],
    }



def test_check_connection_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"fhirVersion": "4.0.1", "software": {"name": "HAPI FHIR"}}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        result = client.check_connection()
    assert result["status"] == "connected"
    assert result["fhir_version"] == "4.0.1"


def test_check_connection_failure(client):
    with patch.object(client._client, "get", side_effect=httpx.ConnectError("refused")):
        result = client.check_connection()
    assert result["status"] == "error"



def test_search_patients_returns_list(client):
    bundle = _mock_bundle("Patient", [{"id": "p1"}, {"id": "p2"}])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = bundle
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        patients = client.search_patients(count=2)
    assert len(patients) == 2
    assert patients[0]["id"] == "p1"


def test_search_patients_empty_bundle(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"resourceType": "Bundle", "entry": [], "link": []}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        assert client.search_patients() == []



def test_fetch_patient_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"resourceType": "Patient", "id": "p1"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        patient = client.fetch_patient("p1")
    assert patient["id"] == "p1"


def test_fetch_patient_not_found(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        with pytest.raises(FHIRNotFoundError):
            client.fetch_patient("nonexistent")



def test_fetch_observations_returns_list(client):
    bundle = _mock_bundle("Observation", [{"id": "obs1"}, {"id": "obs2"}])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = bundle
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        obs = client.fetch_observations("p1")
    assert len(obs) == 2


def test_fetch_sdoh_observations_returns_list(client):
    bundle = _mock_bundle("Observation", [{"id": "sdoh1"}])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = bundle
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        obs = client.fetch_sdoh_observations("p1")
    assert len(obs) == 1



def test_fetch_conditions_returns_list(client):
    bundle = _mock_bundle("Condition", [{"id": "c1", "code": {"text": "Diabetes"}}])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = bundle
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        conditions = client.fetch_conditions("p1")
    assert len(conditions) == 1
    assert conditions[0]["id"] == "c1"



def test_fetch_encounters_returns_list(client):
    bundle = _mock_bundle("Encounter", [{"id": "e1"}, {"id": "e2"}])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = bundle
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        encounters = client.fetch_encounters("p1")
    assert len(encounters) == 2



def test_publish_sdoh_observation_positive(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"resourceType": "Observation", "id": "obs-new"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "post", return_value=mock_resp):
        result = client.publish_sdoh_observation("p1", "housing_insecure", True)
    assert result["id"] == "obs-new"


def test_publish_sdoh_observation_negative(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"resourceType": "Observation", "id": "obs-neg"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "post", return_value=mock_resp):
        result = client.publish_sdoh_observation("p1", "food_insecure", False)
    assert result["id"] == "obs-neg"


def test_publish_sdoh_observation_all_valid_keys(client):
    valid_keys = ["housing_insecure", "food_insecure", "transport_barrier", "unemployed"]
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "x"}
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "post", return_value=mock_resp):
        for key in valid_keys:
            result = client.publish_sdoh_observation("p1", key, True)
            assert result["id"] == "x"


def test_publish_sdoh_observation_invalid_key(client):
    with pytest.raises(ValueError, match="Unknown SDOH feature key"):
        client.publish_sdoh_observation("p1", "made_up_flag", True)


def test_publish_sdoh_observation_server_error(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Server Error"
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=mock_resp
    )
    with patch.object(client._client, "post", return_value=mock_resp):
        with pytest.raises(FHIRError):
            client.publish_sdoh_observation("p1", "housing_insecure", True)



def test_server_error_raises_after_retries(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp):
        with pytest.raises(FHIRError):
            client.fetch_patient("p1")


def test_timeout_raises_fhir_error(client):
    with patch.object(client._client, "get", side_effect=httpx.TimeoutException("timed out")):
        with pytest.raises(FHIRError):
            client.fetch_patient("p1")



def test_pagination_follows_next_link(client):
    page1 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}],
        "link": [{"relation": "next", "url": f"{MOCK_BASE}/Patient?page=2"}],
    }
    page2 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient", "id": "p2"}}],
        "link": [],
    }
    r1, r2 = MagicMock(), MagicMock()
    r1.status_code = 200
    r1.json.return_value = page1
    r1.raise_for_status = MagicMock()
    r2.status_code = 200
    r2.json.return_value = page2
    r2.raise_for_status = MagicMock()
    with patch.object(client._client, "get", side_effect=[r1, r2]):
        patients = client.search_patients(count=10)
    assert len(patients) == 2
    assert {p["id"] for p in patients} == {"p1", "p2"}
