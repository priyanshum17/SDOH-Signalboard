import pytest
from domain.scoring import compute_risk_score, RiskTier

def _patient(
    conditions=None,
    sdoh_flags=None,
    ed_visits_last_year=0,
    age=45,
):
    """Minimal patient dict matching the shape scoring.py expects."""
    return {
        "age": age,
        "conditions": conditions or [],
        "sdoh_flags": sdoh_flags or {},
        "ed_visits_last_year": ed_visits_last_year,
    }


def test_zero_risk_empty_patient():
    result = compute_risk_score(_patient())
    assert result.score == 0
    assert result.tier == RiskTier.LOW


@pytest.mark.parametrize("condition,expected_min_score", [
    ("diabetes", 10),
    ("hypertension", 10),
    ("ckd", 10),
    ("copd", 10),
])
def test_single_chronic_condition_raises_score(condition, expected_min_score):
    result = compute_risk_score(_patient(conditions=[condition]))
    assert result.score >= expected_min_score


def test_multiple_conditions_additive():
    single = compute_risk_score(_patient(conditions=["diabetes"]))
    multi = compute_risk_score(_patient(conditions=["diabetes", "hypertension"]))
    assert multi.score > single.score


def test_ed_visits_raise_score():
    no_ed = compute_risk_score(_patient())
    with_ed = compute_risk_score(_patient(ed_visits_last_year=3))
    assert with_ed.score > no_ed.score


@pytest.mark.parametrize("flag", [
    "housing_insecurity",
    "food_insecurity",
    "transportation_barrier",
    "unemployment",
    "social_isolation",
])
def test_each_sdoh_flag_raises_score(flag):
    result = compute_risk_score(_patient(sdoh_flags={flag: True}))
    assert result.score > 0


def test_multiple_sdoh_flags_additive():
    one = compute_risk_score(_patient(sdoh_flags={"housing_insecurity": True}))
    two = compute_risk_score(_patient(sdoh_flags={
        "housing_insecurity": True,
        "food_insecurity": True,
    }))
    assert two.score > one.score


def test_interaction_multiplier_applied_when_clinical_plus_housing():
    """Homeless + diabetes should score higher than sum of parts."""
    clinical_only = compute_risk_score(_patient(conditions=["diabetes"]))
    sdoh_only = compute_risk_score(_patient(sdoh_flags={"housing_insecurity": True}))
    combined = compute_risk_score(_patient(
        conditions=["diabetes"],
        sdoh_flags={"housing_insecurity": True},
    ))
    assert combined.score > clinical_only.score + sdoh_only.score


def test_age_65_plus_raises_score():
    young = compute_risk_score(_patient(age=40))
    senior = compute_risk_score(_patient(age=70))
    assert senior.score > young.score

@pytest.mark.parametrize("score,expected_tier", [
    (0,   RiskTier.LOW),
    (30,  RiskTier.LOW),
    (50,  RiskTier.MEDIUM),
    (75,  RiskTier.HIGH),
    (100, RiskTier.HIGH),
])
def test_tier_from_score(score, expected_tier):
    """Tier classification is deterministic given a known score."""
    from domain.scoring import score_to_tier
    assert score_to_tier(score) == expected_tier


def test_score_never_exceeds_100():
    worst_case = _patient(
        conditions=["diabetes", "hypertension", "ckd", "copd"],
        sdoh_flags={
            "housing_insecurity": True,
            "food_insecurity": True,
            "transportation_barrier": True,
            "unemployment": True,
            "social_isolation": True,
        },
        ed_visits_last_year=10,
        age=85,
    )
    result = compute_risk_score(worst_case)
    assert result.score <= 100

def test_explanations_non_empty_for_high_risk():
    result = compute_risk_score(_patient(
        conditions=["diabetes"],
        sdoh_flags={"housing_insecurity": True},
    ))
    assert len(result.explanations) > 0


def test_explanations_empty_for_zero_risk():
    result = compute_risk_score(_patient())
    assert result.explanations == []
