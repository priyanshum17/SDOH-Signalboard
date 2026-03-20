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

def test_scoring_high_risk():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": False}, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2 + 1  # housing + food + diabetes + ed + age
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Diabetes" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" in factors

def test_scoring_high_risk_no_age():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": False}, recent_ed_visits=2, age=None)
    assert score == 3 + 3 + 2 + 2  # housing + food + diabetes + ed
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Diabetes" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" not in factors

def test_scoring_high_risk_no_ed():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": False}, recent_ed_visits=0, age=70)
    assert score == 3 + 3 + 2 + 1  # housing + food + diabetes + age
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Diabetes" in factors
    assert "Age ≥ 65" in factors
    assert "High recent ED utilization" not in factors

def test_scoring_high_risk_no_diabetes():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": False, "hypertension": True}, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2 + 1  # housing + food + hypertension + ed + age
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Hypertension" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" in factors
    assert "Diabetes" not in factors

def test_scoring_high_risk_no_hypertension():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": False}, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2 + 1  # housing + food + diabetes + ed + age
    assert "Housing instability" in factors
    assert "Food insecurity" in factors
    assert "Diabetes" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" in factors
    assert "Hypertension" not in factors    
def test_scoring_high_risk_no_housing_instability():
    score, factors = scoring.score_patient({"housing_insecure": False, "food_insecure": True, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": True}, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2  # food + hypertension + age + diabetes + ed
    assert "Food insecurity" in factors
    assert "Hypertension" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" in factors
    assert "Housing instability" not in factors 

def test_scoring_high_risk_no_food_insecurity():
    score, factors = scoring.score_patient({"housing_insecure": True, "food_insecure": False, "transport_barrier": False, "unemployed": False}, {"diabetes": True, "hypertension": True}, recent_ed_visits=2, age=70)
    assert score == 3 + 3 + 2 + 2  # housing + hypertension + ed
    assert "Housing instability" in factors
    assert "Hypertension" in factors
    assert "High recent ED utilization" in factors
    assert "Age ≥ 65" in factors
    assert "Food insecurity" not in factors
    
def test_scoring_high_risk_unemployed():
    score, factors = scoring.score_patient({"housing_insecure": False, "food_insecure": False, "transport_barrier": False, "unemployed": True}, {"diabetes": False, "hypertension": False}, recent_ed_visits=0, age=35)
    assert score == 1 # unemployed
    assert "Housing instability" not in factors
    assert "Food insecurity" not in factors 
    assert "Diabetes" not in factors
    assert "High recent ED utilization" not in factors
    assert "Age ≥ 65" not in factors
    assert "Unemployment/underemployment" in factors