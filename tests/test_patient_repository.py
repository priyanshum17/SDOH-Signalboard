"""Tests for services.patient_repository — SDOH flag parsing and encounter counting."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.patient_repository import (
    _flag_from_observations,
    _condition_flags,
    _encounter_counts,
    _build_patient_row,
)


# ---- SDOH Flag Parsing ---------------------------------------------------

class TestFlagFromObservations:
    def _obs(self, loinc_code: str, answer_code: str) -> dict:
        """Helper to build a minimal FHIR Observation dict."""
        return {
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc_code}]},
            "valueCodeableConcept": {
                "coding": [{"system": "http://loinc.org", "code": answer_code}]
            },
        }

    def test_housing_unstable(self):
        flags = _flag_from_observations([self._obs("71802-3", "LA30186-3")])
        assert flags["housing_insecure"] is True

    def test_housing_stable(self):
        flags = _flag_from_observations([self._obs("71802-3", "LA30185-5")])
        assert flags["housing_insecure"] is False

    def test_food_yes(self):
        flags = _flag_from_observations([self._obs("88122-7", "LA33-6")])
        assert flags["food_insecure"] is True

    def test_food_no(self):
        flags = _flag_from_observations([self._obs("88122-7", "LA32-8")])
        assert flags["food_insecure"] is False

    def test_transport_yes(self):
        flags = _flag_from_observations([self._obs("93030-5", "LA33-6")])
        assert flags["transport_barrier"] is True

    def test_employment_seeking(self):
        flags = _flag_from_observations([self._obs("67875-5", "LA18005-1")])
        assert flags["unemployed"] is True

    def test_employment_fulltime(self):
        flags = _flag_from_observations([self._obs("67875-5", "LA17956-6")])
        assert flags["unemployed"] is False

    def test_stress_high(self):
        flags = _flag_from_observations([self._obs("93038-8", "LA13914-9")])
        assert flags["high_stress"] is True

    def test_stress_low(self):
        flags = _flag_from_observations([self._obs("93038-8", "LA6568-5")])
        assert flags["high_stress"] is False

    def test_empty_observations(self):
        flags = _flag_from_observations([])
        assert all(v is False for v in flags.values())

    def test_multiple_observations(self):
        obs_list = [
            self._obs("71802-3", "LA30186-3"),  # housing unstable
            self._obs("88122-7", "LA33-6"),       # food yes
            self._obs("67875-5", "LA17956-6"),    # employed
        ]
        flags = _flag_from_observations(obs_list)
        assert flags["housing_insecure"] is True
        assert flags["food_insecure"] is True
        assert flags["unemployed"] is False


# ---- Condition Flags ------------------------------------------------------

class TestConditionFlags:
    def _cond(self, snomed_code: str) -> dict:
        return {
            "resourceType": "Condition",
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]},
        }

    def test_diabetes(self):
        flags = _condition_flags([self._cond("44054006")])
        assert flags["diabetes"] is True

    def test_hypertension(self):
        flags = _condition_flags([self._cond("38341003")])
        assert flags["hypertension"] is True

    def test_no_conditions(self):
        flags = _condition_flags([])
        assert flags["diabetes"] is False
        assert flags["hypertension"] is False

    def test_both(self):
        flags = _condition_flags([self._cond("73211009"), self._cond("38341003")])
        assert flags["diabetes"] is True
        assert flags["hypertension"] is True


# ---- Encounter Counts -----------------------------------------------------

class TestEncounterCounts:
    def _enc(self, class_code: str, days_ago: int) -> dict:
        start = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (datetime.now(timezone.utc) - timedelta(days=days_ago) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "resourceType": "Encounter",
            "class": {"code": class_code},
            "type": [{"coding": [{"code": "50849002" if class_code == "EMER" else "308335008"}]}],
            "period": {"start": start, "end": end},
        }

    def test_no_encounters(self):
        total, recent, recent_ed = _encounter_counts([])
        assert total == 0
        assert recent == 0
        assert recent_ed == 0

    def test_recent_ed(self):
        encs = [self._enc("EMER", 30)]
        total, recent, recent_ed = _encounter_counts(encs)
        assert total == 1
        assert recent == 1
        assert recent_ed == 1

    def test_old_encounter_not_recent(self):
        encs = [self._enc("AMB", 200)]
        total, recent, recent_ed = _encounter_counts(encs)
        assert total == 1
        assert recent == 0
        assert recent_ed == 0

    def test_mixed_encounters(self):
        encs = [
            self._enc("EMER", 30),    # recent ED
            self._enc("EMER", 60),    # recent ED
            self._enc("AMB", 100),    # recent ambulatory
            self._enc("AMB", 200),    # old, not counted as recent
        ]
        total, recent, recent_ed = _encounter_counts(encs)
        assert total == 4
        assert recent == 3
        assert recent_ed == 2


# ---- Build Patient Row ---------------------------------------------------

class TestBuildPatientRow:
    def test_builds_row(self):
        patient = {
            "id": "test-123",
            "name": [{"given": ["John"], "family": "Doe"}],
            "gender": "male",
            "birthDate": "1960-01-15",
            "address": [{"city": "Atlanta", "state": "GA"}],
        }
        observations = [
            {
                "code": {"coding": [{"code": "71802-3"}]},
                "valueCodeableConcept": {"coding": [{"code": "LA30186-3"}]},
            }
        ]
        conditions = [
            {"code": {"coding": [{"code": "44054006"}]}}
        ]
        encounters = []

        row = _build_patient_row(patient, observations, conditions, encounters)

        assert row is not None
        assert row["name"] == "John Doe"
        assert row["housing_insecure"] is True
        assert row["diabetes"] is True
        assert row["score"] > 0
        assert len(row["details"]) > 0


# ---- Demo data integrity check -------------------------------------------

class TestDemoData:
    def test_demo_bundles_are_valid_json(self):
        bundle_dir = Path(__file__).resolve().parent.parent / "demo_data" / "fhir_bundles"
        if not bundle_dir.exists():
            return  # skip if demo data not generated

        files = list(bundle_dir.glob("patient_*.json"))
        assert len(files) > 0, "No demo bundle files found"

        for fpath in files:
            with open(fpath) as f:
                bundle = json.load(f)
            assert bundle["resourceType"] == "Bundle"
            assert bundle["type"] == "transaction"
            assert len(bundle["entry"]) > 0

            # Every bundle should have exactly 1 Patient
            patients = [e for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient"]
            assert len(patients) == 1, f"{fpath.name} should have exactly 1 Patient"

    def test_demo_bundles_have_sdoh_observations(self):
        bundle_dir = Path(__file__).resolve().parent.parent / "demo_data" / "fhir_bundles"
        if not bundle_dir.exists():
            return

        for fpath in sorted(bundle_dir.glob("patient_*.json"))[:5]:
            with open(fpath) as f:
                bundle = json.load(f)

            obs = [e for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
            assert len(obs) >= 3, f"{fpath.name} should have at least 3 SDOH observations"
