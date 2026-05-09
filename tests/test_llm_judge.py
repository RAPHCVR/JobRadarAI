from __future__ import annotations

import unittest

from jobradai.llm_judge import (
    _chunks,
    _compact_job,
    _ensure_complete_judgements,
    _merge_judgements,
    _normalise_judgements,
    _select_jobs,
    _sum_usage,
    _judge_chunk,
    _post_json,
    extract_output_text,
    LLMCallError,
    LLMJudgeError,
    LLMSettings,
    parse_json_object,
)
import jobradai.llm_judge as llm_judge


class LLMJudgeTests(unittest.TestCase):
    def test_extract_output_text_from_responses_shape(self) -> None:
        data = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "{\"items\": []}"}],
                }
            ]
        }
        self.assertEqual(extract_output_text(data), '{"items": []}')

    def test_parse_json_object_from_fenced_text(self) -> None:
        parsed = parse_json_object('```json\n{"items": [{"stable_id": "abc"}]}\n```')
        self.assertEqual(parsed["items"][0]["stable_id"], "abc")

    def test_normalise_judgements_clamps_and_filters_unknown_ids(self) -> None:
        jobs = [{"stable_id": "a"}, {"stable_id": "b"}]
        raw = {
            "items": [
                {"stable_id": "a", "fit_score": 130, "priority": "apply_now", "level_fit": "stretch"},
                {"stable_id": "not-present", "fit_score": 100, "priority": "apply_now"},
            ]
        }
        result = _normalise_judgements(raw, jobs)
        self.assertEqual(set(result), {"a"})
        self.assertEqual(result["a"]["fit_score"], 100)
        self.assertEqual(result["a"]["priority"], "apply_now")
        self.assertEqual(result["a"]["level_fit"], "stretch")
        self.assertEqual(result["a"]["salary_check"], "unknown")
        self.assertEqual(result["a"]["start_date_check"], "unknown")

    def test_normalise_judgements_downgrades_too_senior_actionable_priority(self) -> None:
        jobs = [{"stable_id": "senior"}]
        raw = {"items": [{"stable_id": "senior", "fit_score": 85, "priority": "shortlist", "level_fit": "too_senior"}]}
        result = _normalise_judgements(raw, jobs)
        self.assertEqual(result["senior"]["priority"], "skip")
        self.assertEqual(result["senior"]["level_fit"], "too_senior")

    def test_complete_judgements_rejects_missing_batch_items(self) -> None:
        jobs = [{"stable_id": "a"}, {"stable_id": "b"}]
        with self.assertRaises(LLMJudgeError):
            _ensure_complete_judgements({"a": {"fit_score": 80}}, jobs)

    def test_merge_judgements_keeps_deterministic_score_weighted(self) -> None:
        jobs = [
            {
                "stable_id": "a",
                "score": 80,
                "title": "Data Engineer",
                "company": "Acme",
                "url": "https://example.com",
            }
        ]
        judgements = {
            "a": {
                "fit_score": 90,
                "priority": "apply_now",
                "level_fit": "junior_ok",
                "salary_check": "meets_or_likely",
                "remote_check": "meets",
                "start_date_check": "compatible",
                "start_date_evidence": "September 2026",
                "why": ["Bon fit."],
                "risks": [],
                "application_angle": "Mettre en avant RAG/MLOps.",
            }
        }
        [merged] = _merge_judgements(jobs, judgements)
        self.assertEqual(merged["combined_score"], 83.0)
        self.assertEqual(merged["llm_fit_score"], 90)
        self.assertEqual(merged["priority"], "apply_now")
        self.assertEqual(merged["start_date_check"], "compatible")

    def test_compact_job_exposes_experience_signals_to_llm(self) -> None:
        compact = _compact_job(
            {
                "stable_id": "senior",
                "title": "Senior AI Engineer",
                "company": "Acme",
                "url": "https://example.com",
                "required_years": 5,
                "experience_check": "too_senior",
                "experience_evidence": "at least 5 years of professional experience",
            }
        )
        self.assertEqual(compact["required_years"], 5)
        self.assertEqual(compact["experience_check"], "too_senior")
        self.assertIn("5 years", compact["experience_evidence"])

    def test_chunks_and_usage_sum_for_batched_judge(self) -> None:
        self.assertEqual(_chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])
        usage = _sum_usage(
            [
                {"input_tokens": 10, "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 2}},
                {"input_tokens": 7, "output_tokens": 3, "output_tokens_details": {"reasoning_tokens": 1}},
            ]
        )
        self.assertEqual(usage["input_tokens"], 17)
        self.assertEqual(usage["output_tokens"], 8)
        self.assertEqual(usage["output_tokens_details"]["reasoning_tokens"], 3)

    def test_balanced_selection_includes_vie_and_markets_beyond_top(self) -> None:
        jobs = [
            {"stable_id": "top-fr", "score": 90, "market": "france", "source": "ATS"},
            {"stable_id": "top-uk", "score": 89, "market": "uk", "source": "ATS"},
            {"stable_id": "vie-be", "score": 55, "market": "belgium", "source": "Business France VIE"},
            {"stable_id": "sg", "score": 54, "market": "singapore", "source": "ATS"},
            {"stable_id": "ie", "score": 53, "market": "ireland", "source": "ATS"},
        ]
        selected = _select_jobs(jobs, limit=4, mode="balanced")
        ids = [job["stable_id"] for job in selected]
        self.assertIn("vie-be", ids)
        self.assertIn("ie", ids)

    def test_balanced_selection_includes_early_career_beyond_top(self) -> None:
        jobs = [
            {"stable_id": f"top-{index}", "score": 95 - index, "market": "france", "source": "ATS"}
            for index in range(10)
        ]
        jobs.append(
            {
                "stable_id": "graduate-data",
                "score": 45,
                "market": "uk",
                "source": "ATS",
                "title": "Graduate Data Programme",
                "description": "Graduate programme for data engineering, Python and SQL.",
            }
        )
        selected = _select_jobs(jobs, limit=10, mode="balanced")
        self.assertIn("graduate-data", [job["stable_id"] for job in selected])

    def test_vie_selection_falls_back_to_top_when_no_vie(self) -> None:
        jobs = [{"stable_id": "a", "score": 90}, {"stable_id": "b", "score": 80}]
        selected = _select_jobs(jobs, limit=1, mode="vie")
        self.assertEqual([job["stable_id"] for job in selected], ["a"])

    def test_balanced_selection_ranks_vie_by_fit_not_only_allowance_score(self) -> None:
        jobs = [
            {"stable_id": "top", "score": 90, "market": "france", "source": "ATS", "score_parts": {"technical": 90, "role": 90}},
            {
                "stable_id": "weak-vie",
                "score": 70,
                "market": "belgium",
                "source": "Business France VIE",
                "score_parts": {"technical": 5, "role": 50},
            },
            {
                "stable_id": "fit-vie",
                "score": 62,
                "market": "belgium",
                "source": "Business France VIE",
                "score_parts": {"technical": 80, "role": 70},
            },
        ]
        selected = _select_jobs(jobs, limit=2, mode="balanced")
        self.assertEqual(selected[1]["stable_id"], "fit-vie")

    def test_transport_error_does_not_split_batches(self) -> None:
        calls = 0

        def fail_call(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise LLMCallError("transport down")

        original = llm_judge.call_model
        llm_judge.call_model = fail_call
        try:
            settings = LLMSettings(base_url="https://example.com/v1", api_key="test")
            pairs = [
                ({"stable_id": "a"}, {"stable_id": "a"}),
                ({"stable_id": "b"}, {"stable_id": "b"}),
                ({"stable_id": "c"}, {"stable_id": "c"}),
            ]
            with self.assertRaises(LLMCallError):
                _judge_chunk(settings, {}, pairs)
            self.assertEqual(calls, 1)
        finally:
            llm_judge.call_model = original

    def test_post_json_wraps_socket_timeout(self) -> None:
        original = llm_judge.urllib.request.urlopen

        def timeout_call(*args, **kwargs):
            raise TimeoutError("The read operation timed out")

        llm_judge.urllib.request.urlopen = timeout_call
        try:
            with self.assertRaises(LLMCallError) as ctx:
                _post_json("https://example.com/v1/responses", {"model": "x"}, "secret", 1)
            self.assertIn("Erreur reseau LLM", str(ctx.exception))
        finally:
            llm_judge.urllib.request.urlopen = original


if __name__ == "__main__":
    unittest.main()
