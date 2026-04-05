"""Tests for domain.scoring — both legacy and v2 interfaces."""

from domain.scoring import score_patient, score_patient_v2, FactorDetail


# ---- Legacy interface (score_patient → (int, List[str])) ------------------

class TestScorePatientLegacy:
    def test_low_risk_no_flags(self):
        score, factors = score_patient({}, {}, recent_ed_visits=0, age=30)
        assert score == 0
        assert factors == []

    def test_housing_and_food(self):
        sdoh = {"housing_insecure": True, "food_insecure": True}
        score, factors = score_patient(sdoh, {}, recent_ed_visits=0, age=30)
        assert score == 3 + 3
        assert "Housing instability" in factors
        assert "Food insecurity" in factors

    def test_all_sdoh_flags(self):
        sdoh = {
            "housing_insecure": True,
            "food_insecure": True,
            "transport_barrier": True,
            "unemployed": True,
            "high_stress": True,
        }
        score, factors = score_patient(sdoh, {}, recent_ed_visits=0, age=30)
        assert score == 3 + 3 + 2 + 2 + 1  # 11
        assert len(factors) == 5

    def test_conditions_only(self):
        cond = {"diabetes": True, "hypertension": True}
        score, factors = score_patient({}, cond, recent_ed_visits=0, age=30)
        assert score == 2 + 2
        assert "Diabetes" in factors
        assert "Hypertension" in factors

    def test_high_risk_combined(self):
        sdoh = {"housing_insecure": True, "food_insecure": True}
        cond = {"diabetes": True}
        score, factors = score_patient(sdoh, cond, recent_ed_visits=3, age=70)
        # housing(3) + food(3) + diabetes(2) + ED>=3(3) + age>=65(1) = 12
        assert score == 12
        assert "Housing instability" in factors
        assert "Food insecurity" in factors
        assert "Diabetes" in factors
        assert "Age ≥ 65" in factors

    def test_no_age(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=None)
        assert score == 0

    def test_unemployment_is_two_points(self):
        score, factors = score_patient({"unemployed": True}, {}, recent_ed_visits=0, age=30)
        assert score == 2
        assert "Unemployment/underemployment" in factors

    def test_no_housing_flag(self):
        sdoh = {"housing_insecure": False, "food_insecure": True}
        cond = {"diabetes": True, "hypertension": True}
        score, factors = score_patient(sdoh, cond, recent_ed_visits=2, age=70)
        # food(3) + diabetes(2) + htn(2) + ed2(2) + age65(1) = 10
        assert score == 10
        assert "Housing instability" not in factors

    def test_no_food_flag(self):
        sdoh = {"housing_insecure": True, "food_insecure": False}
        cond = {"diabetes": True, "hypertension": True}
        score, factors = score_patient(sdoh, cond, recent_ed_visits=2, age=70)
        # housing(3) + diabetes(2) + htn(2) + ed2(2) + age65(1) = 10
        assert score == 10
        assert "Food insecurity" not in factors


# ---- Tiered ED scoring ---------------------------------------------------

class TestEDTiers:
    def test_zero_ed(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=30)
        assert score == 0

    def test_one_ed_is_one_point(self):
        score, factors = score_patient({}, {}, recent_ed_visits=1, age=30)
        assert score == 1
        assert any("ED" in f for f in factors)

    def test_two_ed_is_two_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=2, age=30)
        assert score == 2

    def test_three_ed_is_three_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=3, age=30)
        assert score == 3

    def test_four_ed_is_still_three_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=4, age=30)
        assert score == 3


# ---- Tiered age scoring --------------------------------------------------

class TestAgeTiers:
    def test_age_30_no_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=30)
        assert score == 0

    def test_age_64_no_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=64)
        assert score == 0

    def test_age_65_is_one_point(self):
        score, factors = score_patient({}, {}, recent_ed_visits=0, age=65)
        assert score == 1
        assert "Age ≥ 65" in factors

    def test_age_74_is_one_point(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=74)
        assert score == 1

    def test_age_75_is_two_points(self):
        score, factors = score_patient({}, {}, recent_ed_visits=0, age=75)
        assert score == 2
        assert "Age ≥ 75" in factors

    def test_age_85_is_two_points(self):
        score, _ = score_patient({}, {}, recent_ed_visits=0, age=85)
        assert score == 2


# ---- V2 interface (FactorDetail) -----------------------------------------

class TestScorePatientV2:
    def test_returns_factor_details(self):
        sdoh = {"housing_insecure": True, "food_insecure": True, "unemployed": True}
        score, details = score_patient_v2(sdoh, {"diabetes": True}, recent_ed_visits=3, age=77)
        assert all(isinstance(d, FactorDetail) for d in details)
        assert score == sum(d.points for d in details)

    def test_factor_detail_has_explanation(self):
        sdoh = {"housing_insecure": True}
        _, details = score_patient_v2(sdoh, {}, recent_ed_visits=0, age=30)
        assert len(details) == 1
        assert details[0].name == "Housing instability"
        assert details[0].points == 3
        assert details[0].severity == "high"
        assert "housing" in details[0].explanation.lower()

    def test_max_score(self):
        sdoh = {
            "housing_insecure": True,
            "food_insecure": True,
            "transport_barrier": True,
            "unemployed": True,
            "high_stress": True,
        }
        cond = {"diabetes": True, "hypertension": True}
        score, _ = score_patient_v2(sdoh, cond, recent_ed_visits=5, age=80)
        # 3+3+2+2+1 + 2+2 + 3 + 2 = 20
        assert score == 20

    def test_as_label(self):
        _, details = score_patient_v2({"food_insecure": True}, {}, recent_ed_visits=0, age=30)
        assert details[0].as_label == "Food insecurity"
