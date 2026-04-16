"""Tests for domain.care_plan_builder."""

from __future__ import annotations

import datetime

import pytest

from domain.care_plan_builder import (
    ActivitySuggestion,
    CarePlanInput,
    build_care_plan_resource,
    suggest_activities,
)


# suggest_activities

def test_suggest_activities_housing_food_map_to_social_referrals():
    suggestions = suggest_activities(["Housing instability", "Food insecurity"])
    titles = {s.title for s in suggestions}
    assert "Housing assistance referral" in titles
    assert "Food security referral" in titles


def test_suggest_activities_dedupes_on_title():
    # Two factor names that would both match the "housing" keyword
    suggestions = suggest_activities(["Housing instability", "housing unstable x"])
    titles = [s.title for s in suggestions]
    assert titles.count("Housing assistance referral") == 1


def test_suggest_activities_empty_input_returns_fallback():
    suggestions = suggest_activities([])
    assert len(suggestions) == 1
    assert suggestions[0].title == "General social needs assessment"


def test_suggest_activities_unknown_factor_returns_fallback():
    suggestions = suggest_activities(["Something entirely unrecognized"])
    assert len(suggestions) == 1
    assert suggestions[0].title == "General social needs assessment"


def test_suggest_activities_ed_utilization_match():
    suggestions = suggest_activities(["High recent ED utilization (2 visits)"])
    titles = {s.title for s in suggestions}
    assert "Care transitions follow-up" in titles


def test_activity_suggestion_to_fhir_shape():
    a = ActivitySuggestion(
        title="Test activity",
        description="Test desc",
        category="social",
    )
    fhir = a.to_fhir()
    assert fhir == {
        "detail": {
            "status": "not-started",
            "code": {"text": "Test activity"},
            "description": "Test desc",
        }
    }


# build_care_plan_resource

FIXED_NOW = datetime.datetime(2026, 4, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)
TAG_SYS = "http://example.org/sdoh"
TAG_CODE = "sdoh-signalboard"
ID_SYS = "http://example.org/ids"


def _minimal_input(**overrides) -> CarePlanInput:
    base = {
        "patient_id": "pt-123",
        "patient_name": "Jane Doe",
        "tier": "HIGH",
        "score": 15,
        "title": "Test CarePlan",
        "activities": [
            ActivitySuggestion(title="A1", description="D1", category="social"),
        ],
        "risk_factors": ["Housing instability"],
    }
    base.update(overrides)
    return CarePlanInput(**base)


def test_build_resource_has_required_fhir_r4_fields():
    inp = _minimal_input()
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert res["resourceType"] == "CarePlan"
    assert res["status"] == "active"
    assert res["intent"] == "plan"
    assert res["title"] == "Test CarePlan"
    assert res["subject"]["reference"] == "Patient/pt-123"
    assert res["subject"]["display"] == "Jane Doe"
    assert res["created"] == FIXED_NOW.isoformat()


def test_build_resource_tag_matches_settings():
    inp = _minimal_input()
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    tag = res["meta"]["tag"][0]
    assert tag["system"] == TAG_SYS
    assert tag["code"] == TAG_CODE


def test_build_resource_identifier_includes_patient_id_and_timestamp():
    inp = _minimal_input()
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    ident = res["identifier"][0]
    assert ident["system"].startswith(ID_SYS)
    assert "pt-123" in ident["value"]
    assert str(int(FIXED_NOW.timestamp())) in ident["value"]


def test_build_resource_description_lists_risk_factors():
    inp = _minimal_input(risk_factors=["Housing instability", "Food insecurity"])
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    desc = res["description"]
    assert "15/20" in desc
    assert "HIGH" in desc
    assert "Housing instability" in desc
    assert "Food insecurity" in desc


def test_build_resource_period_omitted_when_no_dates():
    inp = _minimal_input(period_start=None, period_end=None)
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert "period" not in res


def test_build_resource_period_populated_when_dates_given():
    start = datetime.date(2026, 4, 16)
    end = datetime.date(2026, 7, 15)
    inp = _minimal_input(period_start=start, period_end=end)
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert res["period"] == {"start": "2026-04-16", "end": "2026-07-15"}


def test_build_resource_note_only_when_nonempty():
    no_note = _minimal_input(clinical_note="   ")
    res = build_care_plan_resource(
        no_note, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert "note" not in res

    with_note = _minimal_input(clinical_note="  Follow up in 2 weeks.  ")
    res2 = build_care_plan_resource(
        with_note, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert res2["note"][0]["text"] == "Follow up in 2 weeks."
    assert res2["note"][0]["time"] == FIXED_NOW.isoformat()


def test_build_resource_invalid_status_coerced_to_active():
    inp = _minimal_input(status="nonsense-value")
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert res["status"] == "active"


def test_build_resource_invalid_intent_coerced_to_plan():
    inp = _minimal_input(intent="bogus")
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert res["intent"] == "plan"


def test_build_resource_empty_activities_fills_default():
    inp = _minimal_input(activities=[])
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    assert len(res["activity"]) == 1
    assert res["activity"][0]["detail"]["code"]["text"] == "General social needs assessment"


def test_build_resource_preserves_activity_order():
    acts = [
        ActivitySuggestion(title="First", description="a", category="social"),
        ActivitySuggestion(title="Second", description="b", category="clinical"),
        ActivitySuggestion(title="Third", description="c", category="behavioral"),
    ]
    inp = _minimal_input(activities=acts)
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    titles = [a["detail"]["code"]["text"] for a in res["activity"]]
    assert titles == ["First", "Second", "Third"]


def test_build_resource_category_is_assess_plan():
    inp = _minimal_input()
    res = build_care_plan_resource(
        inp, system_tag=TAG_SYS, code_tag=TAG_CODE, identifier_system=ID_SYS, now=FIXED_NOW
    )
    cat = res["category"][0]
    coding = cat["coding"][0]
    assert coding["code"] == "assess-plan"
