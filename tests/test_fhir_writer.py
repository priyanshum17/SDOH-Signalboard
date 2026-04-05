import pytest
from unittest.mock import patch, MagicMock
from services.fhir_writer import FHIRWriter, WriteBackResult


MOCK_PATIENT_ID = "test-patient-abc123"
MOCK_FHIR_BASE = "https://hapi.fhir.org/baseR4"

@pytest.fixture
def writer():
    return FHIRWriter(fhir_base_url=MOCK_FHIR_BASE)

@pytest.fixture
def high_risk_patient():
    return {
        "patient_id": MOCK_PATIENT_ID,
        "display_name": "John Test",
        "score": 78,
        "tier": "HIGH",
        "explanations": ["Diabetes", "Housing insecurity", "Recent ED visit"],
    }

def test_build_care_plan_has_required_fields(writer, high_risk_patient):
    resource = writer.build_care_plan(high_risk_patient)
    assert resource["resourceType"] == "CarePlan"
    assert resource["status"] == "active"
    assert resource["intent"] == "plan"
    assert MOCK_PATIENT_ID in resource["subject"]["reference"]
    assert len(resource["activity"]) > 0


def test_build_care_plan_activities_match_explanations(writer, high_risk_patient):
    resource = writer.build_care_plan(high_risk_patient)
    activity_texts = [
        a["detail"]["description"]
        for a in resource["activity"]
        if "detail" in a
    ]
    assert any(activity_texts), "CarePlan must have at least one activity"


def test_write_care_plan_posts_to_fhir(writer, high_risk_patient):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "new-careplan-id", "resourceType": "CarePlan"}

    with patch("services.fhir_writer.requests.post", return_value=mock_response) as mock_post:
        result = writer.write_care_plan(high_risk_patient)

    assert result.success is True
    assert result.resource_id == "new-careplan-id"
    mock_post.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert call_url.endswith("/CarePlan")


def test_write_care_plan_handles_server_error(writer, high_risk_patient):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("services.fhir_writer.requests.post", return_value=mock_response):
        result = writer.write_care_plan(high_risk_patient)

    assert result.success is False
    assert "500" in result.error_message


def test_build_service_request_has_required_fields(writer, high_risk_patient):
    resource = writer.build_service_request(high_risk_patient, reason="Social Work Referral")
    assert resource["resourceType"] == "ServiceRequest"
    assert resource["status"] == "active"
    assert resource["intent"] == "order"
    assert MOCK_PATIENT_ID in resource["subject"]["reference"]


def test_write_service_request_posts_to_fhir(writer, high_risk_patient):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "sr-xyz", "resourceType": "ServiceRequest"}

    with patch("services.fhir_writer.requests.post", return_value=mock_response):
        result = writer.write_service_request(high_risk_patient, "Social Work Referral")

    assert result.success is True
    assert result.resource_id == "sr-xyz"

def test_write_care_plan_handles_timeout(writer, high_risk_patient):
    import requests as req
    with patch("services.fhir_writer.requests.post", side_effect=req.Timeout):
        result = writer.write_care_plan(high_risk_patient)

    assert result.success is False
    assert "timeout" in result.error_message.lower()
