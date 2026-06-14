import unittest

from app import app


class SecurityTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.https_headers = {"X-Forwarded-Proto": "https"}

    def test_debug_routes_are_not_exposed(self):
        routes = (
            "/mobile-preview",
            "/api/test-contact-submissions",
            "/api/clear-reviews-cache",
            "/api/place-diagnostics",
            "/api/find-place",
            "/api/nearby-place",
        )

        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(
                    self.client.get(route, headers=self.https_headers).status_code,
                    404,
                )

    def test_security_headers_are_present(self):
        response = self.client.get("/", headers=self.https_headers)
        csp = response.headers["Content-Security-Policy"]

        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("camera=()", response.headers["Permissions-Policy"])

    def test_oversized_contact_submission_is_rejected(self):
        response = self.client.post(
            "/contact",
            data={"additional_details": "x" * (65 * 1024)},
            headers=self.https_headers,
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/contact"))


if __name__ == "__main__":
    unittest.main()
