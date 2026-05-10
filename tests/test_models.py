import unittest

from jobradai.models import Job


class JobModelTests(unittest.TestCase):
    def test_jooble_stable_id_ignores_volatile_query_params(self) -> None:
        first = Job(
            source="Jooble",
            source_type="paid_api",
            title="Data Engineer",
            company="Insight",
            url="https://uk.jooble.org/desc/5686431088002171092?elckey=old&pos=1",
        )
        second = Job(
            source="Jooble",
            source_type="paid_api",
            title="Data Engineer",
            company="Insight",
            url="https://uk.jooble.org/desc/5686431088002171092?elckey=new&pos=2",
        )

        self.assertEqual(first.stable_id, second.stable_id)

    def test_non_jooble_stable_id_keeps_url_specificity(self) -> None:
        first = Job(
            source="Example",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://jobs.example.com/roles/123?department=data",
        )
        second = Job(
            source="Example",
            source_type="ats",
            title="Data Engineer",
            company="Acme",
            url="https://jobs.example.com/roles/123?department=ai",
        )

        self.assertNotEqual(first.stable_id, second.stable_id)


if __name__ == "__main__":
    unittest.main()
