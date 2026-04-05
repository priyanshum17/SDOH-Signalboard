import pytest
from domain.scoring import (
    score_patient_v2,
    score_patient,
    score_to_tier,
    RiskTier,
    MAX_RAW_SCORE,
    FactorDetail,
)


def _no_flags():
    return {"housing_insecure": False, "food_insecure": False,
            "transport_barrier": False, "unemployed": False, "high_stress": False}

def _no_conditions():
    return {"diabetes": False, "hypertension": False}



def test_zero_risk_all_negative():
    score, details = score_patient_v2(_no_flags(), _no_conditions(), 0, 40)
    assert score == 0
    assert details == []



@pytest.mark.parametrize("flag,expected_pts", [
    ("housing_insecure",  3),
    ("food_insecure",     3),
    ("transport_barrier", 2),
    ("unemployed",        2),
    ("high_stress",       1),
])
def test_each_sdoh_flag_adds_correct_points(flag, expected_pts):
    flags = _no_flags()
    flags[flag] = True
    score, details = score_patient_v2(flags, _no_conditions(), 0, 40)
    assert score == expected_pts
    assert len(details) == 1
    assert details[0].points == expected_pts


def test_all_sdoh_flags_additive():
    all_flags = {k: True for k in _no_flags()}
    score, _ = score_patient_v2(all_flags, _no_conditions(), 0, 40)
    assert score == 3 + 3 + 2 + 2 + 1  # = 11



@pytest.mark.parametrize("condition,expected_pts", [
    ("diabetes",     2),
    ("hypertension", 2),
])
def test_each_condition_adds_correct_points(condition, expected_pts):
    conditions = _no_conditions()
    conditions[condition] = True
    score, details = score_patient_v2(_no_flags(), conditions, 0, 40)
    assert score == expected_pts


def test_both_conditions_additive():
    score, _ = score_patient_v2(_no_flags(), {"diabetes": True, "hypertension": True}, 0, 40)
    assert score == 4



@pytest.mark.parametrize("visits,expected_pts", [
    (0, 0),
    (1, 1),
    (2, 2),
    (3, 3),
    (5, 3),   
])
def test_ed_visit_tiers(visits, expected_pts):
    score, _ = score_patient_v2(_no_flags(), _no_conditions(), visits, 40)
    assert score == expected_pts


def test_ed_uses_only_one_tier():
    """Only the highest matching tier should fire, not multiple."""
    _, details = score_patient_v2(_no_flags(), _no_conditions(), 3, 40)
    ed_details = [d for d in details if "ED" in d.name or "utilization" in d.name.lower()]
    assert len(ed_details) == 1



@pytest.mark.parametrize("age,expected_pts", [
    (40,  0),
    (64,  0),
    (65,  1),
    (74,  1),
    (75,  2),
    (90,  2),
])
def test_age_tiers(age, expected_pts):
    score, _ = score_patient_v2(_no_flags(), _no_conditions(), 0, age)
    assert score == expected_pts


def test_age_none_does_not_crash():
    score, _ = score_patient_v2(_no_flags(), _no_conditions(), 0, None)
    assert score == 0



def test_factor_detail_has_required_fields():
    flags = _no_flags()
    flags["housing_insecure"] = True
    _, details = score_patient_v2(flags, _no_conditions(), 0, 40)
    d = details[0]
    assert isinstance(d, FactorDetail)
    assert d.name
    assert d.points > 0
    assert d.severity in ("high", "medium", "low")
    assert d.explanation


def test_factor_detail_as_label():
    flags = _no_flags()
    flags["housing_insecure"] = True
    _, details = score_patient_v2(flags, _no_conditions(), 0, 40)
    assert details[0].as_label == details[0].name



def test_score_patient_returns_strings_not_objects():
    flags = _no_flags()
    flags["housing_insecure"] = True
    score, names = score_patient(flags, _no_conditions(), 0, 40)
    assert isinstance(score, int)
    assert all(isinstance(n, str) for n in names)


def test_score_patient_matches_v2_score():
    flags = {k: True for k in _no_flags()}
    conditions = {"diabetes": True, "hypertension": False}
    s1, _ = score_patient_v2(flags, conditions, 2, 68)
    s2, _ = score_patient(flags, conditions, 2, 68)
    assert s1 == s2



def test_max_raw_score_value():
    """Verify the declared constant matches actual max achievable score."""
    all_flags = {k: True for k in _no_flags()}
    all_conditions = {k: True for k in _no_conditions()}
    score, _ = score_patient_v2(all_flags, all_conditions, 5, 80)
    assert score == MAX_RAW_SCORE



@pytest.mark.parametrize("score,expected_tier", [
    (0,   RiskTier.LOW),
    (6,   RiskTier.LOW),
    (7,   RiskTier.MEDIUM),
    (11,  RiskTier.MEDIUM),
    (12,  RiskTier.HIGH),
    (20,  RiskTier.HIGH),
])
def test_score_to_tier(score, expected_tier):
    assert score_to_tier(score) == expected_tier
