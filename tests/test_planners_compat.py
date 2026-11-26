"""OpenAI 호환 계획기와 맥락 위장 공격 파일 점검. 네트워크를 쓰지 않는다 (가짜 HTTP 응답)."""

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from robotguard.evaluate import FIELDS, run, summarize
from robotguard.guard import LEVELS
from robotguard.planners import (
    COMPAT_PRESETS,
    PLAN_SCHEMA,
    OpenAICompatPlanner,
    build_prompt,
    parse_plan_text,
)
from robotguard.scenarios import DATA_DIR, generate, load_attacks, load_scene


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """요청을 기록하고, 정해진 응답(dict) 또는 예외를 차례로 돌려준다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(json.loads(request.data.decode("utf-8")))
        return FakeResponse(json.dumps(reply).encode("utf-8"))


def completion(content, prompt_tokens=100, completion_tokens=20, finish_reason="stop"):
    return {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def http_error(code):
    return urllib.error.HTTPError("http://fake/v1/chat/completions", code, "err", {}, None)


class ParsePlanTextTest(unittest.TestCase):
    def test_plain_fenced_and_think_wrapped_json(self):
        for text in (
            '{"object_id": "box_red", "zone_id": "zone_a", "reason": "r"}',
            '```json\n{"object_id": "box_red", "zone_id": "zone_a", "reason": "r"}\n```',
            '<think>생각</think>\n{"object_id": "box_red", "zone_id": "zone_a", "reason": "r"}',
        ):
            plan = parse_plan_text(text)
            self.assertIsNone(plan.error, text)
            self.assertEqual((plan.object_id, plan.zone_id), ("box_red", "zone_a"))

    def test_non_json_and_non_object_are_invalid(self):
        for text in ("box_red를 A 구역으로", "[1, 2]", '"box_red"'):
            self.assertEqual(parse_plan_text(text).error, "invalid_json")

    def test_non_string_ids_become_none(self):
        plan = parse_plan_text('{"object_id": 3, "zone_id": null, "reason": "r"}')
        self.assertEqual((plan.object_id, plan.zone_id), (None, None))


class OpenAICompatPlannerTest(unittest.TestCase):
    def setUp(self):
        self.scene = load_scene()
        self.instruction = "빨간 상자를 A 구역으로 옮겨라."
        self.good = completion('{"object_id": "box_red", "zone_id": "zone_a", "reason": "지시대로"}')

    def make(self, replies, **kwargs):
        opener = FakeOpener(replies)
        kwargs.setdefault("retries", 0)
        planner = OpenAICompatPlanner(model="fake-model", base_url="http://fake/v1/", opener=opener, **kwargs)
        return planner, opener

    def test_sends_the_same_prompts_as_claude_planner(self):
        for style in ("naive", "separated"):
            planner, opener = self.make([self.good])
            planner.plan(self.instruction, self.scene, style)
            request = opener.requests[0]
            self.assertEqual(request.full_url, "http://fake/v1/chat/completions")
            body = json.loads(request.data.decode("utf-8"))
            system, user = build_prompt(self.instruction, self.scene, style)
            self.assertEqual(body["messages"], [{"role": "system", "content": system}, {"role": "user", "content": user}])
            self.assertEqual(body["model"], "fake-model")
            self.assertEqual(body["response_format"]["json_schema"]["schema"], PLAN_SCHEMA)

    def test_parses_plan_and_records_usage(self):
        planner, _ = self.make([self.good])
        plan = planner.plan(self.instruction, self.scene, "separated")
        self.assertIsNone(plan.error)
        self.assertEqual((plan.object_id, plan.zone_id), ("box_red", "zone_a"))
        self.assertEqual((plan.input_tokens, plan.output_tokens), (100, 20))
        self.assertIsNotNone(plan.latency_s)
        self.assertEqual((planner.calls, planner.input_tokens, planner.output_tokens), (1, 100, 20))

    def test_response_format_and_extra_body(self):
        planner, opener = self.make([self.good], response_format="none", extra_body={"reasoning_effort": "none"})
        planner.plan(self.instruction, self.scene, "naive")
        body = json.loads(opener.requests[0].data.decode("utf-8"))
        self.assertNotIn("response_format", body)
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(COMPAT_PRESETS["ollama"]["extra_body"], {"reasoning_effort": "none"})
        self.assertIsNone(COMPAT_PRESETS["ollama"]["api_key_env"])

    def test_api_key_comes_from_named_env_var_only(self):
        os.environ["RG_FAKE_KEY"] = "test-value-123"
        try:
            planner, opener = self.make([self.good], api_key_env="RG_FAKE_KEY")
            planner.plan(self.instruction, self.scene, "naive")
            self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer test-value-123")
            self.assertNotIn("test-value-123", planner.usage_summary())
        finally:
            os.environ.pop("RG_FAKE_KEY")
        planner, _ = self.make([self.good], api_key_env="RG_FAKE_KEY_MISSING")
        with self.assertRaises(RuntimeError):
            planner.plan(self.instruction, self.scene, "naive")

    def test_no_key_header_without_env_name(self):
        planner, opener = self.make([self.good])
        planner.plan(self.instruction, self.scene, "naive")
        self.assertIsNone(opener.requests[0].get_header("Authorization"))

    def test_failures_become_plan_errors(self):
        cases = [
            (completion("not json"), "invalid_json"),
            (completion('{"object_id": "box_red"', finish_reason="length"), "max_tokens"),
            (completion(None), "no_text_block"),
            ({"choices": [], "usage": {}}, "no_choice"),
            ({"choices": [{"message": {"content": None, "refusal": "no"}, "finish_reason": "stop"}]}, "refusal"),
        ]
        for reply, expected in cases:
            planner, _ = self.make([reply])
            self.assertEqual(planner.plan(self.instruction, self.scene, "naive").error, expected)

    def test_server_error_is_retried_then_recorded(self):
        with mock.patch("robotguard.planners.time.sleep"):
            planner, opener = self.make([http_error(503), self.good], retries=1)
            plan = planner.plan(self.instruction, self.scene, "naive")
            self.assertIsNone(plan.error)
            self.assertEqual(len(opener.requests), 2)

            planner, _ = self.make([http_error(500)], retries=1)
            self.assertEqual(planner.plan(self.instruction, self.scene, "naive").error, "api_server_error: 500")
            planner, _ = self.make([urllib.error.URLError("down")], retries=0)
            self.assertTrue(planner.plan(self.instruction, self.scene, "naive").error.startswith("api_connection"))

    def test_client_error_stops_the_run(self):
        planner, _ = self.make([http_error(401)])
        with self.assertRaises(RuntimeError):
            planner.plan(self.instruction, self.scene, "naive")

    def test_run_writes_usage_columns_appended_at_the_end(self):
        scenarios = generate(2, 0, self.scene, load_attacks())
        planner, _ = self.make([lambda body: completion('{"object_id": "box_red", "zone_id": "zone_x", "reason": "r"}')])
        rows = run(planner, scenarios, list(LEVELS))
        self.assertEqual(FIELDS[-3:], ["plan_input_tokens", "plan_output_tokens", "plan_latency_s"])
        self.assertTrue(all(set(FIELDS) == set(r) for r in rows))
        self.assertTrue(all(r["plan_input_tokens"] == 100 for r in rows))
        summary = summarize(rows)
        self.assertEqual(summary[0]["mean_plan_input_tokens"], 100.0)
        self.assertEqual(summary[0]["plan_errors"], 0)


class ContextualAttacksTest(unittest.TestCase):
    def test_same_schema_as_original_attacks(self):
        original = load_attacks()
        contextual = load_attacks(DATA_DIR / "attacks_contextual.json")
        self.assertEqual({tuple(sorted(a)) for a in contextual}, {tuple(sorted(original[0]))})
        self.assertFalse({a["id"] for a in original} & {a["id"] for a in contextual})
        self.assertEqual({a["goal"] for a in contextual}, {"forbidden_zone", "misroute"})
        for attack in contextual:
            if attack["goal"] == "forbidden_zone":
                self.assertIn("{zone_name}", attack["template"])

    def test_scenarios_are_generated_and_only_labels_change(self):
        scene = load_scene()
        attacks = load_attacks(DATA_DIR / "attacks_contextual.json")
        scenarios = generate(3, 0, scene, attacks)
        self.assertEqual(len(scenarios), 3 * (1 + len(attacks)))
        for sc in scenarios:
            if sc.condition == "attack" and sc.attack_goal == "forbidden_zone":
                carrier = next(o for o in sc.scene["objects"] if o["id"] == sc.carrier_object)
                self.assertIn("X 구역", carrier["label"])

    def test_default_attacks_file_is_unchanged(self):
        self.assertEqual(len(load_attacks()), 6)


if __name__ == "__main__":
    unittest.main()
