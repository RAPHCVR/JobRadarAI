from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

from jobradai.http import HttpClient, HttpError
from jobradai.redaction import redact_url
from jobradai.sources.ats import _ashby_location, _extract_location, _http_for_feed, fetch_ats_feed
from jobradai.sources.optional import fetch_france_travail, _france_travail_terms, _jobspy_timeout_seconds, _run_text_command
from jobradai.sources.public import (
    fetch_actiris,
    fetch_academictransfer,
    fetch_bundesagentur,
    fetch_business_france_vie,
    fetch_doctorat_gouv,
    fetch_euraxess,
    fetch_forem,
    fetch_germantechjobs,
    fetch_jobicy,
    fetch_jobtechdev_sweden,
    fetch_nav_norway,
    fetch_swissdevjobs,
    fetch_weworkremotely,
)
from jobradai.text import clean_html, days_old


class RateLimitedHttp:
    def fetch_json(self, *args, **kwargs):
        raise HttpError("HTTP failure for https://jobicy.com/api/v2/remote-jobs: HTTP 429 rate limited")


class JobicyFallbackHttp:
    def __init__(self) -> None:
        self.params: list[dict] = []

    def fetch_json(self, url, params=None, **kwargs):
        self.params.append(params or {})
        if (params or {}).get("tag"):
            return {"jobs": []}
        return {
            "jobs": [
                {
                    "id": 1,
                    "jobTitle": "Systems Research Engineer - Software Engineer, Data and ML Infrastructure",
                    "companyName": "Acme AI",
                    "url": "https://jobicy.com/jobs/1",
                    "jobGeo": "Remote Europe",
                    "jobDescription": "Build data and ML infrastructure for research systems.",
                    "jobIndustry": ["Engineering"],
                    "jobType": "Full-time",
                },
                {
                    "id": 2,
                    "jobTitle": "PPC Specialist",
                    "companyName": "Marketing Co",
                    "url": "https://jobicy.com/jobs/2",
                    "jobDescription": "Paid campaigns and SEO.",
                },
            ]
        }


class TextHttp:
    def __init__(self, text: str):
        self.text = text
        self.urls: list[str] = []

    def fetch_text(self, url: str, *args, **kwargs) -> str:
        self.urls.append(url)
        return self.text


class FranceTravailHttp:
    def __init__(self) -> None:
        self.ranges: list[str] = []

    def fetch_json(self, *args, **kwargs):
        return {"access_token": "token"}

    def fetch_text(self, url, params=None, **kwargs):
        current_range = (params or {}).get("range", "")
        self.ranges.append(current_range)
        rows_by_range = {
            "0-1": [
                {
                    "id": "a",
                    "intitule": "Data Engineer",
                    "entreprise": {"nom": "Acme"},
                    "lieuTravail": {"libelle": "Paris"},
                    "origineOffre": {"urlOrigine": "https://example.com/a"},
                    "description": "Python SQL data platform.",
                },
                {
                    "id": "b",
                    "intitule": "ML Engineer",
                    "entreprise": {"nom": "Beta"},
                    "lieuTravail": {"libelle": "Lyon"},
                    "origineOffre": {"urlOrigine": "https://example.com/b"},
                    "description": "Machine learning production.",
                },
            ],
            "2-3": [
                {
                    "id": "b",
                    "intitule": "ML Engineer duplicate",
                    "entreprise": {"nom": "Beta"},
                    "lieuTravail": {"libelle": "Lyon"},
                    "origineOffre": {"urlOrigine": "https://example.com/b"},
                },
                {
                    "id": "c",
                    "intitule": "Analytics Engineer",
                    "entreprise": {"nom": "Gamma"},
                    "lieuTravail": {"libelle": "Nantes"},
                    "origineOffre": {"urlOrigine": "https://example.com/c"},
                    "description": "dbt warehouse analytics.",
                },
            ],
        }
        return json.dumps({"resultats": rows_by_range.get(current_range, [])})


class DoctoratGouvHttp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_json(self, url, params=None, **kwargs):
        self.calls.append(params or {})
        return {
            "content": [
                {
                    "id": "assigned",
                    "sujetAttribue": "oui",
                    "theseTitre": "Doctorat CIFRE en IA deja attribue",
                    "financementTypes": ["CIFRE"],
                    "financementEmployeur": "Acme Research",
                    "etablissementVille": "Paris",
                },
                {
                    "id": "cifre-ai",
                    "sujetAttribue": "non",
                    "theseTitre": "Doctorant CIFRE en IA - NLP, LLM et systemes multi-agents",
                    "resume": "Machine learning, NLP et agents LLM pour outils data.",
                    "profilRecherche": "Python, deep learning, software engineering.",
                    "dateMiseEnLigne": "2026-05-08",
                    "dateDebutThese": "2026-10-01",
                    "dateLimiteCandidature": "2026-06-15",
                    "financementTypes": ["CIFRE"],
                    "financementEmployeur": "Acme AI",
                    "financementOrigine": "entreprise",
                    "niveauAnglaisRequis": "B2",
                    "niveauFrancaisRequis": "B2",
                    "urlCandidature": "https://example.com/apply",
                    "etablissementVille": "Paris",
                    "domaine": "Sciences et technologies de l'information",
                    "specialite": "Informatique",
                },
                {
                    "id": "noise",
                    "sujetAttribue": "non",
                    "theseTitre": "Doctorat en histoire medievale",
                    "resume": "Archives et histoire.",
                },
            ]
        }


class AcademicTransferHttp:
    def __init__(self) -> None:
        self.headers: list[dict] = []
        self.params: list[dict] = []

    def fetch_text(self, url, *args, **kwargs):
        return '<script id="__NUXT_DATA__" type="application/json">["x","y","PUBLIC_TOKEN"]</script>{"$satDataApiPublicAccessToken":2}'

    def fetch_json(self, url, params=None, headers=None, **kwargs):
        self.params.append(params or {})
        self.headers.append(headers or {})
        return {
            "results": [
                {
                    "id": "42",
                    "external_id": "at-42",
                    "is_active": True,
                    "title": "PhD candidate in Machine Learning-Informed Formal Theory Construction",
                    "organisation_name": "Tilburg University",
                    "city": "Tilburg",
                    "country_code": "NL",
                    "absolute_url": "https://www.academictransfer.com/en/jobs/42/phd-machine-learning/",
                    "excerpt": "Machine learning and artificial intelligence research.",
                    "requirements": "Python, statistics and software engineering.",
                    "department_name": "Computer Science",
                    "education_level": "PhD",
                    "contract_type": "Temporary",
                    "available_positions": 1,
                    "min_salary": 3095,
                    "max_salary": 3881,
                    "created_datetime": "2026-05-08T00:00:00+00:00",
                    "end_date": "2026-06-15",
                },
                {
                    "id": "postdoc",
                    "is_active": True,
                    "title": "Postdoc Machine Learning",
                    "excerpt": "AI research.",
                },
            ],
            "next": None,
        }


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


class SmartRecruitersHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def fetch_json(self, url, params=None, **kwargs):
        self.calls.append((url, params or {}))
        if url == "https://api.smartrecruiters.test/postings":
            offset = (params or {}).get("offset")
            if offset == 0:
                return {
                    "content": [
                        {
                            "id": "1",
                            "name": "Data Engineer I",
                            "ref": "https://api.smartrecruiters.test/postings/1",
                            "location": {"fullLocation": "Berlin, Germany"},
                        },
                        {
                            "id": "2",
                            "name": "Closed Data Engineer",
                            "ref": "https://api.smartrecruiters.test/postings/2",
                        },
                    ]
                }
            return {
                "content": [
                    {"id": "3", "name": "Duplicate page", "ref": "https://api.smartrecruiters.test/postings/1"},
                    {"id": "4", "name": "Senior Data Engineer", "ref": "https://api.smartrecruiters.test/postings/4"},
                ]
            }
        if url.endswith("/1"):
            return {
                "id": "1",
                "name": "Data Engineer I",
                "active": True,
                "visibility": "PUBLIC",
                "postingUrl": "https://jobs.smartrecruiters.test/company/1-data-engineer",
                "applyUrl": "https://jobs.smartrecruiters.test/company/1-data-engineer?oga=true",
                "releasedDate": "2026-05-08T00:00:00Z",
                "location": {"fullLocation": "Berlin, Germany", "hybrid": True},
                "typeOfEmployment": {"label": "Full-time"},
                "experienceLevel": {"label": "Entry Level"},
                "function": {"label": "Information Technology"},
                "department": {"label": "Data"},
                "customField": [{"valueLabel": "Data Engineering"}],
                "jobAd": {"sections": {"jobDescription": {"text": "<p>Python SQL pipelines</p>"}}},
            }
        if url.endswith("/2"):
            return {"id": "2", "name": "Closed Data Engineer", "active": False, "visibility": "PUBLIC"}
        if url.endswith("/4"):
            return {"id": "4", "name": "Senior Data Engineer", "active": True, "visibility": "PUBLIC"}
        raise AssertionError(url)


class BundesagenturHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    def fetch_json(self, url, params=None, headers=None, **kwargs):
        self.calls.append((params or {}, headers or {}))
        return {
            "stellenangebote": [
                {
                    "beruf": "Data Engineer",
                    "titel": "Data Engineer (m/w/d)",
                    "refnr": "10001-42-S",
                    "arbeitsort": {"ort": "Berlin", "region": "Berlin", "land": "Deutschland"},
                    "arbeitgeber": "Example GmbH",
                    "aktuelleVeroeffentlichungsdatum": "2026-05-08",
                    "eintrittsdatum": "2026-09-01",
                    "externeUrl": "https://example.com/apply",
                },
                {
                    "beruf": "KI-Engineer",
                    "titel": "AI Engineer (m/w/d)",
                    "refnr": "10001-43-S",
                    "arbeitsort": {"ort": "München", "region": "Bayern", "land": "Deutschland"},
                    "arbeitgeber": "AI GmbH",
                    "aktuelleVeroeffentlichungsdatum": "2026-05-07",
                },
                {
                    "beruf": "Data Engineer",
                    "titel": "Data Engineer",
                    "refnr": "10001-44-S",
                    "arbeitsort": {"ort": "Wien", "region": "Wien", "land": "Österreich"},
                    "arbeitgeber": "AT GmbH",
                    "aktuelleVeroeffentlichungsdatum": "2026-05-07",
                },
            ]
        }


class JobTechDevSwedenHttp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_json(self, url, params=None, **kwargs):
        self.calls.append(params or {})
        return {
            "hits": [
                {
                    "id": "30979729",
                    "headline": "Data Engineer",
                    "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/30979729",
                    "application_details": {"url": "https://example.se/apply"},
                    "employer": {"name": "Techrytera AB"},
                    "workplace_address": {"city": "Stockholm", "region": "Stockholm", "country": "Sverige"},
                    "description": {"text_formatted": "<p>Python SQL Snowflake DBT</p>"},
                    "publication_date": "2026-05-08T00:00:00",
                    "salary_description": "Fast månadslön",
                    "employment_type": {"label": "Vanlig anställning"},
                    "duration": {"label": "Tills vidare"},
                    "working_hours_type": {"label": "Heltid"},
                    "occupation": {"label": "Dataingenjör"},
                    "occupation_group": {"label": "Data/IT"},
                },
                {
                    "id": "removed",
                    "headline": "Removed Data Engineer",
                    "removed": True,
                },
            ]
        }


class NavNorwayHttp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_json(self, url, params=None, **kwargs):
        self.calls.append(params or {})
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "uuid": "dd98f9c1-06a0-4fcc-9289-8401afd5cf65",
                            "status": "ACTIVE",
                            "title": "Senior data engineer",
                            "businessName": "Data Engineering, Statnett",
                            "published": "2026-04-30T00:00:00+02:00",
                            "medium": "talentech",
                            "generatedSearchMetadata": {"shortSummary": "Python SQL Databricks data platform"},
                            "locationList": [
                                {"city": "OSLO", "county": "OSLO", "country": "NORGE"},
                                {"city": "TRONDHEIM", "county": "TRØNDELAG", "country": "NORGE"},
                            ],
                            "properties": {
                                "workLanguage": ["Norsk", "Engelsk"],
                                "searchtagsai": ["Azure", "Databricks", "Python", "SQL"],
                                "education": ["Bachelor"],
                                "experience": ["Mye"],
                                "keywords": "data engineer; data platform",
                            },
                            "categoryList": [{"name": "Senior Data Engineer"}],
                            "occupationList": [{"level1": "IT", "level2": "Drift, vedlikehold"}],
                        }
                    },
                    {
                        "_source": {
                            "uuid": "inactive",
                            "status": "INACTIVE",
                            "title": "Inactive Data Engineer",
                        }
                    },
                    {
                        "_source": {
                            "uuid": "denmark",
                            "status": "ACTIVE",
                            "title": "Data Engineer Denmark",
                            "businessName": "DK Data",
                            "locationList": [{"city": "KØBENHAVN", "county": "HOVEDSTADEN", "country": "DANMARK"}],
                            "properties": {"searchtagsai": ["Python"]},
                        }
                    },
                ]
            }
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

    def test_smartrecruiters_uses_queries_details_and_human_urls(self) -> None:
        http = SmartRecruitersHttp()
        jobs = fetch_ats_feed(
            {
                "name": "Delivery Hero",
                "type": "smartrecruiters",
                "url": "https://api.smartrecruiters.test/postings",
                "queries": ["data engineer"],
                "page_size": 2,
                "max_pages": 2,
                "fetch_details": True,
                "include_title_keywords": ["data engineer"],
                "exclude_title_keywords": ["senior"],
            },
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://jobs.smartrecruiters.test/company/1-data-engineer")
        self.assertEqual(jobs[0].apply_url, "https://jobs.smartrecruiters.test/company/1-data-engineer?oga=true")
        self.assertTrue(jobs[0].remote)
        self.assertIn("Python SQL pipelines", jobs[0].description)
        self.assertIn("Entry Level", jobs[0].employment_type)
        page_calls = [call for call in http.calls if call[0] == "https://api.smartrecruiters.test/postings"]
        self.assertEqual([call[1].get("offset") for call in page_calls], [0, 2])
        self.assertEqual(page_calls[0][1].get("q"), "data engineer")

    def test_days_old_parses_epoch_ms(self) -> None:
        self.assertIsNotNone(days_old(1777500000000))

    def test_jobicy_rate_limit_is_best_effort(self) -> None:
        jobs = fetch_jobicy({"queries": [{"term": "AI Engineer"}]}, RateLimitedHttp())
        self.assertEqual(jobs, [])

    def test_jobicy_falls_back_to_global_feed_with_local_filter(self) -> None:
        http = JobicyFallbackHttp()
        jobs = fetch_jobicy(
            {"queries": [{"term": "Data Engineer"}], "jobicy": {"fallback_count": 2}},
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertIn("Data and ML Infrastructure", jobs[0].title)
        self.assertEqual(jobs[0].company, "Acme AI")
        self.assertTrue(any("tag" not in params for params in http.params))

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

    def test_weworkremotely_rss_maps_relevant_remote_job(self) -> None:
        rss = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Acme AI: Data Engineer</title>
            <link>https://weworkremotely.com/remote-jobs/acme-data</link>
            <pubDate>Fri, 08 May 2026 20:55:30 GMT</pubDate>
            <description><![CDATA[<p><strong>Headquarters:</strong> Remote Europe</p><p>Python ML pipelines.</p>]]></description>
          </item>
          <item><title>Acme AI: Product Marketing Lead</title><link>https://example.com/nope</link><description>Marketing</description></item>
        </channel></rss>"""
        jobs = fetch_weworkremotely(
            {"queries": [{"term": "Data Engineer"}], "weworkremotely": {"feeds": ["https://example.com/rss"], "max_items": 10}},
            TextHttp(rss),
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "We Work Remotely")
        self.assertTrue(jobs[0].remote)
        self.assertEqual(jobs[0].company, "Acme AI")
        self.assertEqual(jobs[0].location, "Remote Europe")

    def test_swiss_and_german_tech_rss_extract_salary_from_title(self) -> None:
        rss = """<?xml version="1.0"?>
        <rss><channel><item>
          <title>Data Engineer @ Acme AG [CHF 80'000 - 110'000]</title>
          <link>https://swissdevjobs.ch/jobs/acme-data</link>
          <description>Python, Databricks and machine learning platforms.</description>
        </item></channel></rss>"""
        swiss = fetch_swissdevjobs({"queries": [{"term": "Data Engineer"}], "swissdevjobs": {"feed": "https://example.com/rss"}}, TextHttp(rss))
        german = fetch_germantechjobs({"queries": [{"term": "Data Engineer"}], "germantechjobs": {"feed": "https://example.com/rss"}}, TextHttp(rss))
        self.assertEqual(swiss[0].company, "Acme AG")
        self.assertEqual(swiss[0].salary, "CHF 80'000 - 110'000")
        self.assertEqual(swiss[0].country, "Switzerland")
        self.assertEqual(german[0].country, "Germany")

    def test_german_tech_rss_can_scan_beyond_1000_items_when_configured(self) -> None:
        items = [
            f"<item><title>Marketing Lead @ Noise {index}</title><link>https://example.com/noise-{index}</link><description>Sales.</description></item>"
            for index in range(1100)
        ]
        items.append(
            "<item><title>AI Engineer @ Late AG</title><link>https://example.com/late-ai</link><description>LLM, Python and MLOps.</description></item>"
        )
        rss = "<?xml version=\"1.0\"?><rss><channel>" + "".join(items) + "</channel></rss>"
        config = {"queries": [{"term": "Data Engineer"}], "germantechjobs": {"feed": "https://example.com/rss"}}
        limited = fetch_germantechjobs({**config, "germantechjobs": {"feed": "https://example.com/rss", "max_items": 1000}}, TextHttp(rss))
        widened = fetch_germantechjobs({**config, "germantechjobs": {"feed": "https://example.com/rss", "max_items": 1200}}, TextHttp(rss))
        self.assertEqual(limited, [])
        self.assertEqual(len(widened), 1)
        self.assertEqual(widened[0].title, "AI Engineer")

    def test_euraxess_extracts_deadline_from_official_portal_html(self) -> None:
        html = """
        <article class="ecl-content-item">
          <ul class="ecl-content-block__primary-meta-container"><li><a>Research Lab</a></li><li>Posted on: 8 May 2026</li></ul>
          <h3 class="ecl-content-block__title"><a href="/jobs/434842"><span>PhD Candidate - Synthetic Data and AI for Energy Systems</span></a></h3>
          <div class="ecl-content-block__description"><p>Machine learning, data science and AI research.</p></div>
          <div>Work Locations: Number of offers: 1, Ireland, Dublin Research Field: Computer science Researcher Profile: First Stage Researcher Funding Programme: Not funded Application Deadline: 1 Jun 2026 - 23:00 (Europe/Dublin)</div>
        </article>
        """
        jobs = fetch_euraxess({"queries": [{"term": "AI Engineer"}], "euraxess": {"endpoint": "https://example.com/jobs", "max_pages": 1}}, TextHttp(html))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_type, "official_portal")
        self.assertIn("Synthetic Data and AI", jobs[0].title)
        self.assertIn("1 Jun 2026", jobs[0].deadline)

    def test_euraxess_keeps_msca_doctoral_ai_but_not_non_tech(self) -> None:
        html = """
        <article class="ecl-content-item">
          <h3 class="ecl-content-block__title"><a href="/jobs/1"><span>MSCA Doctoral Network - Trustworthy LLM Systems</span></a></h3>
          <div class="ecl-content-block__description"><p>Doctoral Candidate on trustworthy AI safety and large language model evaluation.</p></div>
          <div>Work Locations: France Application Deadline: 1 Jul 2026 - 12:00</div>
        </article>
        <article class="ecl-content-item">
          <h3 class="ecl-content-block__title"><a href="/jobs/2"><span>MSCA Doctoral Candidate in Medieval History</span></a></h3>
          <div class="ecl-content-block__description"><p>Archives and cultural studies.</p></div>
          <div>Work Locations: France Application Deadline: 1 Jul 2026 - 12:00</div>
        </article>
        """
        jobs = fetch_euraxess({"euraxess": {"endpoint": "https://example.com/jobs", "max_pages": 1}}, TextHttp(html))
        self.assertEqual(len(jobs), 1)
        self.assertIn("Trustworthy LLM", jobs[0].title)

    def test_doctorat_gouv_maps_open_thesis_and_skips_assigned(self) -> None:
        http = DoctoratGouvHttp()
        jobs = fetch_doctorat_gouv(
            {
                "doctorat_gouv": {
                    "queries": ["CIFRE"],
                    "max_queries": 1,
                    "page_size": 20,
                    "max_pages": 1,
                }
            },
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "Doctorat.gouv.fr")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].company, "Acme AI")
        self.assertEqual(jobs[0].country, "France")
        self.assertEqual(jobs[0].deadline, "2026-06-15")
        self.assertEqual(jobs[0].employment_type, "Doctorat CIFRE")
        self.assertIn("anglais B2", jobs[0].tags)
        self.assertEqual(http.calls[0]["sortField"], "dateMiseEnLigne")

    def test_academictransfer_uses_public_token_and_maps_salary(self) -> None:
        http = AcademicTransferHttp()
        jobs = fetch_academictransfer(
            {
                "academictransfer": {
                    "queries": ["phd machine learning"],
                    "max_queries": 1,
                    "page_size": 2,
                    "max_pages": 1,
                }
            },
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "AcademicTransfer")
        self.assertEqual(jobs[0].source_type, "public_api")
        self.assertEqual(jobs[0].country, "Netherlands")
        self.assertEqual(jobs[0].salary, "EUR 3095 - 3881 monthly")
        self.assertEqual(jobs[0].deadline, "2026-06-15")
        self.assertIn("Tilburg", jobs[0].location)
        self.assertEqual(http.params[0]["search"], "phd machine learning")
        self.assertEqual(http.headers[0]["Authorization"], "Bearer PUBLIC_TOKEN")

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

    def test_forem_can_prepend_source_specific_queries(self) -> None:
        http = ForemHttp()
        fetch_forem(
            {
                "forem": {"max_queries": 1, "queries": ["Data Quality Analyst"]},
                "queries": [{"term": "data engineer"}],
            },
            http,
        )
        self.assertEqual(http.params[0]["where"], '"Data Quality Analyst"')

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

    def test_actiris_can_prepend_source_specific_queries(self) -> None:
        http = ActirisHttp()
        fetch_actiris(
            {
                "actiris": {"max_queries": 1, "page_size": 5, "max_pages": 1, "queries": ["Data Quality Analyst"]},
                "queries": [{"term": "data engineer"}],
            },
            http,
        )
        self.assertEqual(http.bodies[0]["offreFilter"], {"texte": "Data Quality Analyst"})

    def test_bundesagentur_maps_official_jobs_and_uses_public_key(self) -> None:
        http = BundesagenturHttp()
        jobs = fetch_bundesagentur(
            {
                "bundesagentur": {
                    "queries": ["Data Engineer"],
                    "max_queries": 1,
                    "page_size": 3,
                    "max_pages": 1,
                }
            },
            http,
        )
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].source, "Bundesagentur Jobsuche")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].url, "https://example.com/apply")
        self.assertIn("Berlin", jobs[0].location)
        self.assertIn("Germany", jobs[0].country)
        self.assertIn("jobdetail/10001-43-S", jobs[1].url)
        self.assertEqual(http.calls[0][0]["was"], "Data Engineer")
        self.assertEqual(http.calls[0][1]["X-API-Key"], "jobboerse-jobsuche")
        self.assertFalse(any(job.country == "Austria" for job in jobs))

        jobs_with_at = fetch_bundesagentur(
            {
                "bundesagentur": {
                    "queries": ["Data Engineer"],
                    "max_queries": 1,
                    "page_size": 3,
                    "max_pages": 1,
                    "countries": ["Deutschland", "Österreich"],
                }
            },
            http,
        )
        self.assertEqual(jobs_with_at[-1].country, "Austria")

    def test_jobtechdev_sweden_maps_official_jobs(self) -> None:
        http = JobTechDevSwedenHttp()
        jobs = fetch_jobtechdev_sweden(
            {
                "jobtechdev_sweden": {
                    "queries": ["Data Engineer"],
                    "max_queries": 1,
                    "page_size": 2,
                    "max_pages": 1,
                }
            },
            http,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "JobTechDev Sweden")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].country, "Sweden")
        self.assertEqual(jobs[0].apply_url, "https://example.se/apply")
        self.assertIn("Stockholm", jobs[0].location)
        self.assertIn("Snowflake", jobs[0].description)
        self.assertIn("Tills vidare", jobs[0].employment_type)
        self.assertEqual(http.calls[0]["q"], "Data Engineer")

    def test_nav_norway_maps_public_jobs(self) -> None:
        http = NavNorwayHttp()
        jobs = fetch_nav_norway(
            {
                "nav_norway": {
                    "queries": ["Data Engineer"],
                    "max_queries": 1,
                    "page_size": 3,
                    "max_pages": 1,
                }
            },
            http,
        )
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].source, "NAV Arbeidsplassen")
        self.assertEqual(jobs[0].source_type, "official_api")
        self.assertEqual(jobs[0].country, "Norway")
        self.assertIn("arbeidsplassen.nav.no/stillinger/stilling/dd98f9c1", jobs[0].url)
        self.assertIn("OSLO", jobs[0].location)
        self.assertIn("Databricks", jobs[0].tags)
        self.assertIn("Bachelor", jobs[0].employment_type)
        self.assertEqual(jobs[1].country, "Denmark")
        self.assertEqual(http.calls[0]["q"], "Data Engineer")

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
            max_queries=12,
        )
        self.assertIn("architecte data", terms)
        self.assertIn("data scientist", terms)
        self.assertIn("LLM", terms)
        self.assertIn("RAG", terms)
        self.assertEqual(len(terms), len({term.casefold() for term in terms}))

    def test_france_travail_paginates_and_deduplicates_search_results(self) -> None:
        http = FranceTravailHttp()
        with mock.patch.dict(
            os.environ,
            {"FRANCE_TRAVAIL_CLIENT_ID": "client", "FRANCE_TRAVAIL_CLIENT_SECRET": "secret"},
        ):
            jobs, reason = fetch_france_travail(
                {
                    "queries": [{"term": "Data Engineer"}],
                    "france_travail": {"max_queries": 1, "page_size": 2, "max_pages": 3},
                },
                http,
            )
        self.assertEqual(reason, "")
        self.assertEqual(http.ranges, ["0-1", "2-3", "4-5"])
        self.assertEqual([job.raw_id for job in jobs], ["a", "b", "c"])

    def test_jobspy_direct_timeout_is_bounded_and_configurable(self) -> None:
        self.assertEqual(_jobspy_timeout_seconds({}), 240)
        self.assertEqual(_jobspy_timeout_seconds({"timeout_seconds": 5}), 30)
        self.assertEqual(_jobspy_timeout_seconds({"timeout_seconds": 1200}), 900)
        self.assertEqual(_jobspy_timeout_seconds({"timeout_seconds": 90}), 90)

    def test_run_text_command_captures_output_without_stdout_pipe(self) -> None:
        completed = _run_text_command(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
            input_text="ok",
            cwd=Path.cwd(),
            timeout_seconds=10,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "OK")

    def test_run_text_command_timeout_returns_control(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            _run_text_command(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                input_text="",
                cwd=Path.cwd(),
                timeout_seconds=1,
            )

    def test_http_error_redacts_env_secret(self) -> None:
        os.environ["JOBRADAR_TEST_API_KEY"] = "super-secret-token"
        try:
            error = HttpClient(timeout=0, retries=0)._with_params("https://example.com", {"api_key": "super-secret-token"})
            self.assertNotIn("super-secret-token", redact_url(error))
        finally:
            os.environ.pop("JOBRADAR_TEST_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
