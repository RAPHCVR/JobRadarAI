from __future__ import annotations

import unittest

from jobradai.config import load_config
from jobradai.models import Job
from jobradai.scoring import (
    _annual_salary_estimate,
    _required_years,
    _tokens,
    experience_requirement,
    infer_market,
    salary_normalization,
    score_jobs,
)


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(load_env=False)

    def test_llm_data_engineer_dublin_scores_high(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Senior Data Engineer, LLM Platform",
            company="Example AI",
            url="https://example.com/job",
            location="Dublin, Ireland",
            description="Python SQL Spark Databricks RAG LLM evaluation orchestration MLOps Kubernetes production platform",
            posted_at="2026-04-30T00:00:00Z",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertEqual(scored.market, "ireland")
        self.assertGreater(scored.score, 70)
        self.assertIn("technical", scored.score_parts)
        self.assertIn("work_mode", scored.score_parts)
        self.assertIn("location_fit", scored.score_parts)
        self.assertIn("market_practicality", scored.score_parts)
        self.assertIn("early_career", scored.score_parts)

    def test_product_manager_with_ai_description_is_not_top_ranked(self) -> None:
        jobs = [
            Job(
                source="test",
                source_type="ats",
                title="Senior Product Manager - AI Analytics",
                company="Example",
                url="https://example.com/pm",
                location="Zurich, Switzerland",
                description="SQL RAG LLM research cloud governance analytics platform",
                posted_at="2026-04-30T00:00:00Z",
            ),
            Job(
                source="test",
                source_type="ats",
                title="Data Engineer - AI Analytics",
                company="Example",
                url="https://example.com/de",
                location="Zurich, Switzerland",
                description="Python SQL data engineering RAG LLM orchestration cloud",
                posted_at="2026-04-30T00:00:00Z",
            ),
        ]
        scored = score_jobs(jobs, self.config.profile, self.config.markets)
        self.assertEqual(scored[0].title, "Data Engineer - AI Analytics")
        self.assertLess(scored[1].score_parts["role"], scored[0].score_parts["role"])

    def test_commercial_solution_engineer_is_penalized(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Commercial Solution Engineer - Data Cloud",
            company="Example",
            url="https://example.com/solutions",
            location="Berlin, Germany",
            description="Python SQL data engineering LLM RAG cloud platform",
            posted_at="2026-04-30T00:00:00Z",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertLess(scored.score_parts["role"], 30)

    def test_cv_research_signals_are_rewarded(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="AI Research Engineer, Mechanistic Interpretability",
            company="Example",
            url="https://example.com/research",
            location="Paris, France",
            description="Python LLM explainability AI safety evaluation interpretability research LangGraph",
            posted_at="2026-04-30T00:00:00Z",
            salary="55 000 EUR annuel",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertGreater(scored.score, 70)
        self.assertGreater(scored.score_parts["technical"], 65)

    def test_graduate_ai_program_is_not_penalized_as_bad_junior_signal(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Graduate AI Engineer Programme",
            company="Example",
            url="https://example.com/grad-ai",
            location="Paris, France",
            description=(
                "Graduate programme starting September 2026 for AI engineering, Python, SQL, "
                "LLM evaluation, RAG, MLOps and production platform work."
            ),
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertGreater(scored.score_parts["early_career"], 80)
        self.assertGreater(scored.score_parts["role"], 85)
        self.assertFalse(any(reason == "Penalite: graduate" for reason in scored.reasons))
        self.assertTrue(any("new-grad" in reason or "graduate" in reason.lower() for reason in scored.reasons))

    def test_cifre_ai_doctorate_is_scored_as_research_opportunity_not_internship(self) -> None:
        job = Job(
            source="test",
            source_type="official_api",
            title="Doctorant CIFRE IA - Machine Learning",
            company="Example AI",
            url="https://example.com/cifre-ai",
            location="Paris, France",
            description=(
                "Convention industrielle de formation par la recherche with an R&D team. "
                "Applied research on explainability, LLM evaluation, Python, SQL and machine learning."
            ),
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertGreater(scored.score_parts["early_career"], 80)
        self.assertGreater(scored.score_parts["technical"], 35)
        self.assertGreater(scored.score_parts["role"], 80)
        self.assertFalse(any("Stage/alternance" in reason for reason in scored.reasons))
        self.assertTrue(any("CIFRE" in reason or "recherche" in reason.lower() for reason in scored.reasons))

    def test_academic_doctorate_stays_opportunistic_below_industrial_cifre(self) -> None:
        academic = Job(
            source="Doctorat.gouv.fr",
            source_type="official_api",
            title="PhD Candidate Machine Learning and LLM Evaluation",
            company="University Lab",
            url="https://example.com/phd",
            location="Paris, France",
            description="University doctoral research in machine learning, LLM evaluation, Python and deep learning.",
        )
        industrial = Job(
            source="Doctorat.gouv.fr",
            source_type="official_api",
            title="Doctorant CIFRE IA - Machine Learning",
            company="Example AI",
            url="https://example.com/cifre-ai",
            location="Paris, France",
            description="CIFRE with an R&D team on LLM evaluation, Python and machine learning.",
        )
        scored = score_jobs([academic, industrial], self.config.profile, self.config.markets)
        by_url = {job.url: job for job in scored}
        self.assertLess(by_url["https://example.com/phd"].score, by_url["https://example.com/cifre-ai"].score)
        self.assertLess(by_url["https://example.com/phd"].score_parts["doctoral_scope"], 0)
        self.assertGreater(by_url["https://example.com/cifre-ai"].score_parts["doctoral_scope"], 0)
        self.assertTrue(any("opportuniste" in reason.lower() for reason in by_url["https://example.com/phd"].reasons))

    def test_senior_five_year_role_is_level_penalized_for_junior_profile(self) -> None:
        junior = Job(
            source="test",
            source_type="ats",
            title="Machine Learning Engineer",
            company="Example",
            url="https://example.com/ml",
            location="Paris, France",
            description="Python LLM evaluation MLOps production platform.",
        )
        senior = Job(
            source="test",
            source_type="ats",
            title="Senior Machine Learning Engineer",
            company="Example",
            url="https://example.com/senior-ml",
            location="Paris, France",
            description="Python LLM evaluation MLOps production platform. 5+ years of experience required.",
        )
        scored = score_jobs([senior, junior], self.config.profile, self.config.markets)
        by_url = {job.url: job for job in scored}
        self.assertLess(by_url["https://example.com/senior-ml"].score_parts["role"], 70)
        self.assertGreater(
            by_url["https://example.com/ml"].score_parts["role"],
            by_url["https://example.com/senior-ml"].score_parts["role"],
        )

    def test_required_years_handles_at_least_and_qualified_experience_phrasing(self) -> None:
        self.assertEqual(
            _required_years("You are a backend engineer with at least 5 years of professional experience."),
            5,
        )
        self.assertEqual(
            _required_years("Minimum of 3 years experience with modern scripting languages."),
            3,
        )
        self.assertEqual(
            _required_years("2+ years of relevant engineering experience building AI products."),
            2,
        )
        requirement = experience_requirement(
            "Senior AI Engineer",
            "You are a backend engineer with at least 5 years of professional experience.",
        )
        self.assertEqual(requirement.required_years, 5)
        self.assertEqual(requirement.check, "too_senior")
        self.assertIn("5 years", requirement.evidence)

    def test_salary_monthly_is_annualized_against_minimum(self) -> None:
        self.assertEqual(_annual_salary_estimate("Mensuel de 2800 Euros a 3500 Euros"), 42000)
        self.assertEqual(_annual_salary_estimate("Annuel de 35000.0 Euros a 50000.0 Euros"), 50000)
        self.assertEqual(_annual_salary_estimate("Annuel de 52 000,00 Euros a 57 000,00 Euros"), 57000)

    def test_salary_normalization_converts_common_currencies(self) -> None:
        swiss = salary_normalization("Salary: CHF 80'000 - 110'000 per year")
        self.assertEqual(swiss.currency, "CHF")
        self.assertEqual(swiss.period, "annual")
        self.assertEqual(swiss.annual_eur, 113300)
        german = salary_normalization("Salary: 60.000 - 100.000 € per year")
        self.assertEqual(german.currency, "EUR")
        self.assertEqual(german.annual_eur, 100000)
        job = Job(
            source="test",
            source_type="official_api",
            title="Data Engineer",
            company="Example",
            url="https://example.com/salary",
            location="Paris, France",
            description="Python SQL data engineering",
            salary="Mensuel de 2800 Euros a 3500 Euros",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertLess(scored.score_parts["salary"], 45)

    def test_hybrid_and_major_city_preferences_are_rewarded(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="AI Platform Engineer",
            company="Example",
            url="https://example.com/hybrid",
            location="Paris, France",
            description="Hybrid role with 2 days remote per week. Python LLM RAG Kubernetes platform.",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertGreater(scored.score_parts["work_mode"], 80)
        self.assertGreater(scored.score_parts["location_fit"], 85)

    def test_remote_location_is_rewarded_as_remote_work_mode(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Data Engineer",
            company="Example",
            url="https://example.com/remote",
            location="Germany, Remote; Netherlands, Remote",
            description="Python SQL data engineering RAG LLM platform.",
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertGreater(scored.score_parts["work_mode"], 90)

    def test_infer_market_remote(self) -> None:
        job = Job(
            source="test",
            source_type="public_api",
            title="AI Engineer",
            company="Remote Co",
            url="https://example.com",
            location="Remote Europe",
            remote=True,
        )
        market = infer_market(job, self.config.markets["markets"])
        self.assertEqual(market.key, "remote_europe")

    def test_infer_market_dublin_california_is_not_ireland(self) -> None:
        job = Job(
            source="test",
            source_type="ats",
            title="Software Engineer",
            company="Example",
            url="https://example.com",
            location="US-CA-Dublin",
        )
        market = infer_market(job, self.config.markets["markets"])
        self.assertEqual(market.key, "other")

    def test_infer_market_does_not_match_alias_substrings(self) -> None:
        jobs = [
            Job(
                source="test",
                source_type="ats",
                title="Applied AI Engineer",
                company="Example",
                url="https://example.com/agentic",
                location="Budapest, Hungary",
                tags=["Agentic AI"],
            ),
            Job(
                source="test",
                source_type="ats",
                title="Account Manager Ukraine",
                company="Example",
                url="https://example.com/ukraine",
                location="Kyiv, Ukraine",
            ),
            Job(
                source="test",
                source_type="ats",
                title="Backend Engineer",
                company="Example",
                url="https://example.com/argentina",
                location="Buenos Aires, Argentina",
            ),
        ]
        markets = [infer_market(job, self.config.markets["markets"]).key for job in jobs]
        self.assertEqual(markets, ["other", "other", "other"])

    def test_vie_indemnity_is_not_scored_like_cdi_gross_salary(self) -> None:
        job = Job(
            source="Business France VIE",
            source_type="official_api",
            title="Data Analyst (H/F)",
            company="Safran",
            url="https://mon-vie-via.businessfrance.fr/offres/242713",
            location="Gloucester, United Kingdom",
            description="Python SQL data pipelines cloud databases",
            salary="Indemnite VIE mensuelle 2704.01 EUR",
            employment_type="VIE 12 mois",
            tags=["vie", "volontariat international en entreprise"],
        )
        [scored] = score_jobs([job], self.config.profile, self.config.markets)
        self.assertEqual(scored.market, "uk")
        self.assertGreaterEqual(scored.score_parts["salary"], 70)
        self.assertTrue(any("Indemnite VIE" in reason for reason in scored.reasons))

    def test_rag_token_requires_word_boundary(self) -> None:
        tokens = _tokens("Pragmatic coordinator for storage and onboarding")
        self.assertNotIn("rag", tokens)
        self.assertNotIn("aks", _tokens("Own onboarding tasks and stakeholder updates"))
        self.assertIn("rag", _tokens("RAG evaluation engineer"))

    def test_multi_word_profile_keywords_are_tokenized(self) -> None:
        tokens = _tokens("Distributed systems, data quality, GitHub Actions and Azure DevOps.")
        self.assertIn("distributed_systems", tokens)
        self.assertIn("data_quality", tokens)
        self.assertIn("github_actions", tokens)
        self.assertIn("azure_devops", tokens)


if __name__ == "__main__":
    unittest.main()
