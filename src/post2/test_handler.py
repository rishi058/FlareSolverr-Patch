import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dtos import V1RequestBase
from post2 import handler


class RequestPost2VerificationTests(unittest.TestCase):
    def test_detects_verification_challenge(self):
        recipe = {
            "trigger": {
                "status_code": 403,
                "field": "gate",
                "equals": "VERIFY",
            }
        }
        self.assertTrue(handler._requires_verification({"gate": "VERIFY"}, 403, recipe))
        self.assertFalse(handler._requires_verification({"gate": "OTHER"}, 403, recipe))
        self.assertFalse(handler._requires_verification({"gate": "VERIFY"}, 200, recipe))

    @patch.object(handler.db, "get")
    @patch.object(handler, "_verify_and_cache")
    @patch.object(handler, "_do_post")
    def test_verifies_and_retries_original_post(self, do_post, verify_and_cache, db_get):
        initial_session = {
            "cookies": [],
            "headers": {"User-Agent": "test"},
            "cached_at": 1,
        }
        verified_session = {
            "cookies": [{"name": "tdl_pass", "value": "pass"}],
            "headers": {"User-Agent": "test"},
        }
        db_get.return_value = initial_session
        verify_and_cache.return_value = verified_session
        do_post.side_effect = [
            ({"success": False, "code": "CHALLENGE_REQUIRED"}, 403, None),
            ({"errno": 0, "list": [{"server_filename": "video.mp4"}]}, 200, None),
        ]

        response = handler.cmd_request_post2(V1RequestBase({
            "cmd": "request.post2",
            "base_url": "https://protected.example/",
            "post_endpoint": "api/resource",
            "post_json_body": {"resource": "example"},
            "verification": {
                "trigger": {
                    "status_code": 403,
                    "field": "code",
                    "equals": "CHALLENGE_REQUIRED",
                },
                "endpoint": "api/session/verify",
                "site_key": "test-site-key",
                "token_field": "token",
                "success_field": "success",
            },
        }))

        self.assertEqual(response.status, "ok")
        self.assertEqual(response.target_url_response["status_code"], 200)
        self.assertEqual(do_post.call_count, 2)
        verify_and_cache.assert_called_once_with(
            "https://protected.example/",
            {
                "trigger": {
                    "status_code": 403,
                    "field": "code",
                    "equals": "CHALLENGE_REQUIRED",
                },
                "endpoint": "api/session/verify",
                "site_key": "test-site-key",
                "token_field": "token",
                "success_field": "success",
            },
        )

    def test_merges_verification_response_cookies(self):
        response_cookies = Mock()
        response_cookies.__iter__ = Mock(return_value=iter([
            SimpleNamespace(
                name="tdl_pass",
                value="verified",
                path="/api",
                secure=True,
                domain="teraboxdl.site",
                expires=123,
            )
        ]))

        result = handler._merge_response_cookies(
            [{"name": "cf_clearance", "value": "clear"}],
            response_cookies,
        )

        self.assertEqual({cookie["name"] for cookie in result}, {"cf_clearance", "tdl_pass"})
        self.assertEqual(next(cookie for cookie in result if cookie["name"] == "tdl_pass")["value"], "verified")

    @patch.object(handler.db, "get")
    @patch.object(handler, "_verify_and_cache")
    @patch.object(handler, "_do_post")
    def test_reuses_verification_refreshed_by_concurrent_request(
        self, do_post, verify_and_cache, db_get
    ):
        initial_session = {
            "cookies": [],
            "headers": {"User-Agent": "test"},
            "cached_at": 1,
        }
        refreshed_session = {
            "cookies": [{"name": "pass", "value": "refreshed"}],
            "headers": {"User-Agent": "test"},
            "cached_at": 2,
        }
        db_get.side_effect = [initial_session, refreshed_session]
        do_post.side_effect = [
            ({"gate": "VERIFY"}, 403, None),
            ({"result": "ok"}, 200, None),
        ]

        response = handler.cmd_request_post2(V1RequestBase({
            "cmd": "request.post2",
            "base_url": "https://protected.example/",
            "post_endpoint": "api/resource",
            "post_json_body": {"resource": "example"},
            "verification": {
                "trigger": {
                    "status_code": 403,
                    "field": "gate",
                    "equals": "VERIFY",
                },
                "endpoint": "api/session/verify",
                "site_key": "test-site-key",
                "token_field": "token",
            },
        }))

        self.assertEqual(response.target_url_response["status_code"], 200)
        verify_and_cache.assert_not_called()
        self.assertIs(do_post.call_args_list[1].args[2], refreshed_session)


if __name__ == "__main__":
    unittest.main()
