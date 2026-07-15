import unittest
from unittest.mock import Mock, patch

import app as app_module


app = app_module.app


class SecurityTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app_module.TURNSTILE_ENABLED = False
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

    def test_turnstile_widget_is_rendered_when_enabled(self):
        with (
            patch.object(app_module, "TURNSTILE_ENABLED", True),
            patch.object(app_module, "TURNSTILE_SITE_KEY", "test-site-key"),
        ):
            response = self.client.get("/contact", headers=self.https_headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="cf-turnstile"', response.data)
        self.assertIn(b'data-sitekey="test-site-key"', response.data)
        self.assertIn(b"https://challenges.cloudflare.com/turnstile/v0/api.js", response.data)

    def test_turnstile_verification_accepts_valid_token(self):
        turnstile_response = Mock()
        turnstile_response.raise_for_status.return_value = None
        turnstile_response.json.return_value = {
            "success": True,
            "hostname": "360-epoxy.com",
            "action": "contact",
        }

        with (
            app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.10"}),
            patch.object(app_module, "TURNSTILE_ENABLED", True),
            patch.object(app_module, "TURNSTILE_SECRET_KEY", "test-secret-key"),
            patch.object(app_module.requests, "post", return_value=turnstile_response) as post,
        ):
            self.assertTrue(app_module.verify_turnstile_token("valid-token"))

        post.assert_called_once_with(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": "test-secret-key",
                "response": "valid-token",
                "remoteip": "203.0.113.10",
            },
            timeout=5,
        )

    def test_turnstile_verification_rejects_missing_token(self):
        with (
            app.test_request_context("/"),
            patch.object(app_module, "TURNSTILE_ENABLED", True),
            patch.object(app_module.requests, "post") as post,
        ):
            self.assertFalse(app_module.verify_turnstile_token(""))

        post.assert_not_called()

    def test_oversized_contact_submission_is_rejected(self):
        response = self.client.post(
            "/contact",
            data={"additional_details": "x" * (65 * 1024)},
            headers=self.https_headers,
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/contact"))

    def test_sms_checkboxes_are_separate_and_unchecked_by_default(self):
        response = self.client.get("/contact", headers=self.https_headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="sms_consent" value="yes"', response.data)
        self.assertIn(b'name="marketing_sms_consent" value="yes"', response.data)
        self.assertNotIn(b'name="sms_consent" value="yes" checked', response.data)
        self.assertNotIn(b'name="marketing_sms_consent" value="yes" checked', response.data)

    def test_transactional_sms_checkbox_does_not_opt_into_marketing(self):
        webhook_response = Mock()
        webhook_response.raise_for_status.return_value = None

        form_data = {
            "first_name": "Alex",
            "last_name": "Customer",
            "email": "alex@example.com",
            "phone": "(385)-555-1234",
            "project_type": "garage_floor",
            "square_feet": "500",
            "desired_timeline": "within_1_month",
            "street_address": "123 Main St",
            "city": "Salt Lake City",
            "state": "Utah",
            "zip_code": "84101",
            "additional_details": "Looking for a garage floor estimate.",
            "sms_consent": "yes",
            "minimum_project_acknowledged": "yes",
        }

        with (
            patch.object(app_module, "GHL_WEBHOOK_ENABLED", True),
            patch.object(app_module, "GHL_CONTACT_WEBHOOK_URL", "https://example.com/webhook"),
            patch.object(app_module.requests, "post", return_value=webhook_response) as post,
        ):
            response = self.client.post(
                "/contact",
                data=form_data,
                headers=self.https_headers,
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        payload = post.call_args.kwargs["json"]
        self.assertTrue(payload["sms_consent"])
        self.assertFalse(payload["marketing_sms_consent"])
        self.assertEqual(payload["sms_consent_status"], "opted_in")
        self.assertEqual(payload["marketing_sms_consent_status"], "not_opted_in")
        self.assertIsNotNone(payload["sms_consent_timestamp_utc"])
        self.assertIsNone(payload["marketing_sms_consent_timestamp_utc"])


if __name__ == "__main__":
    unittest.main()
