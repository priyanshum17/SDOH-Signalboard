from domain import scoring


def test_scoring_flags():
    sdoh = {"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}
    cond = {"diabetes": True, "hypertension": False}
    score, factors = scoring.score_patient(sdoh, cond, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2 + 1  # housing + food + diabetes + ed + age
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Diabetes" in factors


def test_scoring_low_risk():
    score, factors = scoring.score_patient({}, {}, recent_ed_visits=0, age=30)
    assert score == 0
    assert factors == []
