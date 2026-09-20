import unittest
from unittest.mock import Mock, patch

import requests
import app as app_module


class ReviewTests(unittest.TestCase):
    def test_new_api_preserves_order_and_attribution(self):
        response = Mock()
        response.json.return_value = {
            "displayName": {"text": "360Epoxy"},
            "rating": 4.7,
            "userRatingCount": 12,
            "reviews": [
                {"rating": 3, "text": {"text": "First result"},
                 "authorAttribution": {"displayName": "Customer", "uri": "https://maps.google.com/profile", "photoUri": "https://example.com/avatar.png"},
                 "googleMapsUri": "https://maps.google.com/review", "relativePublishTimeDescription": "a month ago"},
                {"rating": 5},
            ],
        }
        with patch.object(app_module, "GOOGLE_API_KEY", "test-key"), patch.object(app_module.requests, "get", return_value=response) as get:
            data, status = app_module.fetch_google_reviews()
        self.assertEqual(status, 200)
        self.assertEqual(data["total_reviews"], 12)
        self.assertEqual([r["rating"] for r in data["reviews"]], [3, 5])
        self.assertEqual(data["reviews"][0]["author_url"], "https://maps.google.com/profile")
        self.assertEqual(data["reviews"][0]["google_maps_url"], "https://maps.google.com/review")
        self.assertEqual(data["reviews"][1]["text"], "")
        self.assertIn("places.googleapis.com/v1/places/", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"]["X-Goog-Api-Key"], "test-key")

    def test_upstream_failure_is_safe_and_retryable(self):
        with patch.object(app_module, "GOOGLE_API_KEY", "test-key"):
            for error in [requests.Timeout("private details"), requests.HTTPError("private details"), ValueError("private details")]:
                with self.subTest(error=type(error).__name__), patch.object(app_module.requests, "get", side_effect=error):
                    data, status = app_module.fetch_google_reviews()
                    self.assertEqual(status, 502)
                    self.assertNotIn("private", str(data))

    def test_missing_credentials_do_not_call_google(self):
        with patch.object(app_module, "GOOGLE_API_KEY", None), patch.object(app_module.requests, "get") as get:
            self.assertEqual(app_module.fetch_google_reviews()[1], 500)
            get.assert_not_called()

    def test_route_does_not_cache_error_or_success(self):
        client = app_module.app.test_client()
        with patch.object(app_module, "fetch_google_reviews", side_effect=[({"error": "Unavailable"}, 502), ({"reviews": []}, 200)]) as fetch:
            first = client.get('/api/reviews', headers={"X-Forwarded-Proto": "https"})
            second = client.get('/api/reviews', headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(first.status_code, 502)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers['Cache-Control'], 'no-store')
        self.assertEqual(fetch.call_count, 2)
