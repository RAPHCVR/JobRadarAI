from __future__ import annotations

import json
import os
import unittest

from jobradai.http import HttpClient, HttpError
from jobradai.redaction import redact_url
from jobradai.sources.ats import _ashby_location, _extract_location, _http_for_feed
from jobradai.sources.optional import _france_travail_terms
from jobradai.sources.public import fetch_actiris, fetch_business_france_vie, fetch_forem, fetch_jobicy
from jobradai.text import clean_html, days_old


class RateLimitedHttp:
    def fetch_json(self, *args, **kwargs):
        raise HttpError("HTTP failure for https://jobicy.com/api/v2/remote-jobs: HTTP 429 rate limited")


class BusinessFranceHttp:
    def fetch_json(self, *args, **kwargs):
        return {
            "result": [
                {
                    "id": 242713,
                    "organizationName": "SAFRAN LANDING SYSTEMS",
                    "missionTitle": "Data Analyst (H/F)",
                    "missionDuration": 12,
                    "missionType": "VIE",
                    "missionTypeEn": "VIE",
                    "missionDescription": "Python SQL data pipelines",
                    "missionProfile": "Professional English required",
                    "cityName": "GLOUCESTER",
                    "cityNameEn": "GLOUCESTER",
                    "countryName": "ROYAUME-UNI",
                    "countryNameEn": "UNITED KINGDOM",
                    "countryId": "GB",
                    "reference": "VIE242713",
                    "indemnite": 2704.01,
                    "teleworkingAvailable": True,
                    "startBroadcastDate": "2026-05-01T00:00:00",
                },
                {
                    "id": 1,
                    "organizationName": "Administration",
                    "missionTitle": "VIA Analyst",
                    "missionType": "VIA",
                },
            ]
        }


class BusinessFrancePagedHttp:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def fetch_json(self, *args, **kwargs):
        body = json.loads(kwargs["body"].decode("utf-8"))
        self.bodies.append(body)
        skip = body.get("skip", 0)
        if skip == 0:
            return {
                "count": 3,
                "result": [
                    {
                        "id": 11,
                        "organizationName": "A",
                        "missionTitle": "Data VIE",
                        "missionType": "VIE",
                        "missionTypeEn": "VIE",
                    },
                    {
                        "id": 12,
                        "organizationName": "B",
                        "missionTitle": "VIA Data",
                        "missionType": "VIA",
                        "missionTypeEn": "VIA",
                    },
                ],
            }
        return {
            "count": 3,
            "result": [
                {
                    "id": 13,
                    "organizationName": "C",
                    "missionTitle": "AI VIE",
                    "missionType": "VIE",
                    "missionTypeEn": "VIE",
                }
            ],
        }


class ForemHttp:
    def __init__(self) -> None:
        self.params: list[dict] = []

    def fetch_json(self, *args, **kwargs):
        self.params.append(kwargs.get("params") or (args[1] if len(args) > 1 else {}))
        return {
            "results": [
                {
                    "numerooffreforem": "1",
                    "titreoffre": "Mecanicien poids lourds (H/F/X)",
                    "nomemployeur": "Garage",
                    "url": "https://www.leforem.be/recherche-offres/offre-detail/1",
                },
                {
                    "numerooffreforem": "1887153",
                    "titreoffre": "Data Engineer Health Sector (H/F/X)",
                    "lieuxtravaillocalite": ["SAINT-GILLES"],
                    "lieuxtravailregion": ["Belgique", "RÉGION DE BRUXELLES-CAPITALE"],
                    "typecontrat": "Durée indéterminée",
                    "nomemployeur": "Smals",
                    "regimetravail": "Temps plein",
                    "niveauxetudes": ["Baccalauréat universitaire ou équivalent"],
                    "langues": ["Français"],
                    "secteurs": ["Autres activités informatiques"],
                    "source": "StepStone",
                    "url": "https://www.leforem.be/recherche-offres/offre-detail/1887153",
                    "datedebutdiffusion": "2026-05-05",
                    "metier": "Administrateur / Administratrice de base de données",
                },
                {
                    "numerooffreforem": "1887153",
                    "titreoffre": "Duplicate",
                    "url": "https://www.leforem.be/recherche-offres/offre-detail/1887153",
                },
            ]
        }


class ActirisHttp:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def fetch_json(self, *args, **kwargs):
        self.bodies.append(json.loads(kwargs["body"].decode("utf-8")))
        return {
            "total": 1,
            "items": [
                {
                    "reference": "1",
                    "employeur": {"nomFr": "SMALS - MVM"},
                    "titreFr": "Windows System Engineer H/F/X",
                    "typeContrat": "CDI",
                    "codePays": "BE",
                    "communeFr": "Saint-Gilles",
                    "codePostal": "1060",
                    "typeContratLibelle": "Durée indéterminée",
                    "dateCreation": "2026-05-06T00:00:00+02:00",
                },
                {
                    "reference": "5836063",
                    "employeur": {"nomFr": "SMALS - MVM"},
                    "titreFr": "Data Engineer Health Sector H/F/X",
                    "typeContrat": "CDI",
                    "typeOffre": "Hrxml",
                    "codePays": "BE",
                    "communeFr": "Saint-Gilles",
                    "codePostal": "1060",
                    "typeContratLibelle": "Durée indéterminée",
                    "dateCreation": "2026-05-06T00:00:00+02:00",
                }
            ],
        }


class SourceHelpersTests(unittest.TestCase):
    def test_clean_html(self) -> None:
        self.assertEqual(clean_html("<p>Hello<br>World</p>"), "Hello World")

    def test_extract_location_dict(self) -> None:
        self.assertEqual(_extract_location({"city": "Dublin", "country": "Ireland"}), "Dublin, Ireland")

    def test_extract_location_list(self) -> None:
        self.assertEqual(
            _extract_location([{"city": "Paris", "country": "France"}, {"city": "Dublin", "country": "Ireland"}]),
            "Paris, France, Dublin, Ireland",
        )

    def test_ashby_location_includes_secondary_locations(self) -> None:
        self.assertEqual(
            _ashby_location(
                {
                    "locationName": "London, UK",
                    "secondaryLocations": [{"locationName": "Dublin, Ireland"}, {"locationName": "Paris, France"}],
                }
            ),
            "London, UK, Dublin, Ireland, Paris, France",
        )

    def test_ats_feed_can_override_http_timeout_without_global_change(self) -> None:
        base = HttpClient(timeout=25, retries=2)
        base.user_agent = "test-agent"
        scoped = _http_for_feed({"timeout": 90, "retries": 3}, base)
        self.assertIsNot(scoped, base)
        self.assertEqual(scoped.timeout, 90)
        self.assertEqual(scoped.retries, 3)
        self.assertEqual(scoped.user_agent, "test-agent")
        self.assertIs(_http_for_feed({}, base), base)

    def test_days_old_parses_epoch_ms(self) -> None:
        self.assertIsNotNone(days_old(1777500000000))

    def test_jobicy_rate_limit_is_best_effort(self) -> None:
        jobs = fetch_jobicy({"queries": [{"term": "AI Engineer"}]}, RateLimitedHttp())
        self.assertEqual(jobs, [])

    def test_business_france_vie_maps_official_offer(self) -> None:
        jobs = fetch_business_france_vie({"business_france_vie": {"queries": ["data"], "max_queries": 1}}, BusinessFranceHttp())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "Business France VIE")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].employment_type, "VIE 12 mois")
        self.assertIn("UNITED KINGDOM", jobs[0].location)
        self.assertIn("2704.01", jobs[0].salary)
        self.assertTrue(jobs[0].remote)

    def test_business_france_vie_scan_all_paginates_and_filters_via(self) -> None:
        http = BusinessFrancePagedHttp()
        jobs = fetch_business_france_vie(
            {"business_france_vie": {"scan_all": True, "page_size": 2, "max_results": 10}},
            http,
        )
        self.assertEqual([job.title for job in jobs], ["Data VIE", "AI VIE"])
        self.assertEqual([body["skip"] for body in http.bodies], [0, 2])
        self.assertNotIn("query", http.bodies[0])

    def test_forem_maps_open_data_offer_and_uses_where_filter(self) -> None:
        http = ForemHttp()
        jobs = fetch_forem({"forem": {"max_queries": 1}, "queries": [{"term": "data engineer"}]}, http)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "Le Forem Open Data")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].country, "Belgium")
        self.assertEqual(jobs[0].company, "Smals")
        self.assertIn("SAINT-GILLES", jobs[0].location)
        self.assertIn("StepStone", jobs[0].tags)
        self.assertEqual(http.params[0]["where"], '"data engineer"')

    def test_actiris_maps_public_offer_and_pages(self) -> None:
        http = ActirisHttp()
        jobs = fetch_actiris(
            {"actiris": {"max_queries": 1, "page_size": 5, "max_pages": 1}, "queries": [{"term": "data engineer"}]},
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "Actiris")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].country, "Belgium")
        self.assertEqual(jobs[0].company, "SMALS - MVM")
        self.assertIn("reference=5836063", jobs[0].url)
        self.assertEqual(http.bodies[0]["pageOption"], {"page": 1, "pageSize": 5})

    def test_redact_url_removes_query_and_jooble_path_secrets(self) -> None:
        self.assertIn("api_key=%5BREDACTED%5D", redact_url("https://example.com/search?api_key=secret&x=1"))
        self.assertNotIn("jooble-secret", redact_url("https://jooble.org/api/jooble-secret"))

    def test_france_travail_terms_keep_extra_french_queries_after_dedupe(self) -> None:
        terms = _france_travail_terms(
            {
                "queries": [
                    {"term": "LLM Engineer", "priority": 10},
                    {"term": "Data Engineer", "priority": 9},
                    {"term": "Graduate Data Engineer", "priority": 8, "category": "early_career"},
                ]
            },
            max_queries=9,
        )
        self.assertIn("architecte data", terms)
        self.assertIn("LLM", terms)
        self.assertIn("RAG", terms)
        self.assertEqual(len(terms), len({term.casefold() for term in terms}))

    def test_http_error_redacts_env_secret(self) -> None:
        os.environ["JOBRADAR_TEST_API_KEY"] = "super-secret-token"
        try:
            error = HttpClient(timeout=0, retries=0)._with_params("https://example.com", {"api_key": "super-secret-token"})
            self.assertNotIn("super-secret-token", redact_url(error))
        finally:
            os.environ.pop("JOBRADAR_TEST_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
