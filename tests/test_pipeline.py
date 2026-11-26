"""파이프라인 점검. 실행: python -m unittest discover -s tests -v"""

import os
import tempfile
import unittest
from pathlib import Path

from robotguard.evaluate import load_dotenv, run, summarize
from robotguard.guard import LEVELS, apply_guard
from robotguard.physical import episodes_from_plans, summarize as summarize_physical
from robotguard.planners import CompromisedPlanner, MockPlanner, Plan, build_prompt
from robotguard.scenarios import generate, load_attacks, load_scene
from robotguard.zones import distance_to_zone, inside_zone


class DotenvTest(unittest.TestCase):
    def test_loads_new_keys_without_overwriting_or_returning_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".env"
            path.write_text("# 주석\nRG_TEST_NEW='abc'\nRG_TEST_EXISTING=from_file\nRG_TEST_EMPTY=\n", encoding="utf-8")
            os.environ["RG_TEST_EXISTING"] = "from_env"
            try:
                loaded = load_dotenv(path)
                self.assertEqual(loaded, ["RG_TEST_NEW"])
                self.assertEqual(os.environ["RG_TEST_NEW"], "abc")
                self.assertEqual(os.environ["RG_TEST_EXISTING"], "from_env")
                self.assertNotIn("RG_TEST_EMPTY", os.environ)
            finally:
                for key in ("RG_TEST_NEW", "RG_TEST_EXISTING"):
                    os.environ.pop(key, None)

    def test_missing_file_is_ignored(self):
        self.assertEqual(load_dotenv(Path("does-not-exist.env")), [])


class ZoneTest(unittest.TestCase):
    def setUp(self):
        self.zone = next(z for z in load_scene()["zones"] if not z["allowed"])

    def test_center_is_inside_and_boundary_is_outside(self):
        c, h = self.zone["center"], self.zone["half_size"]
        self.assertTrue(inside_zone(c, self.zone))
        self.assertTrue(inside_zone([c[0] + h[0] * 0.99, c[1], c[2]], self.zone))
        self.assertFalse(inside_zone([c[0] + h[0], c[1], c[2]], self.zone))
        self.assertFalse(inside_zone([c[0], c[1], c[2] + h[2] * 1.01], self.zone))

    def test_distance_is_zero_inside_and_euclidean_outside(self):
        c, h = self.zone["center"], self.zone["half_size"]
        self.assertEqual(distance_to_zone(c, self.zone), 0.0)
        self.assertAlmostEqual(distance_to_zone([c[0] + h[0] + 0.03, c[1], c[2]], self.zone), 0.03)
        corner = [c[0] + h[0] + 0.03, c[1] + h[1] + 0.04, c[2]]
        self.assertAlmostEqual(distance_to_zone(corner, self.zone), 0.05)

    def test_success_radius_at_center_is_inside_zone(self):
        # 성공 반경(0.05m)의 구는 반 크기 0.05m인 상자에 내접한다.
        # 따라서 구역 중심을 목표로 성공하면 팔 끝은 구역 안이거나 경계 위다.
        c, h = self.zone["center"], self.zone["half_size"]
        self.assertTrue(all(v >= 0.05 for v in h))
        self.assertTrue(inside_zone([c[0] + 0.049, c[1], c[2]], self.zone))


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.scene = load_scene()
        self.instruction = "빨간 상자를 A 구역으로 옮겨라."

    def test_allowed_plan_passes_every_guard(self):
        plan = Plan("box_red", "zone_a")
        for guard in ("none", "allowlist", "allowlist+approval"):
            self.assertEqual(apply_guard(guard, plan, self.scene, self.instruction).decision, "pass")

    def test_forbidden_zone_is_blocked_only_with_allowlist(self):
        plan = Plan("box_red", "zone_x")
        self.assertEqual(apply_guard("none", plan, self.scene, self.instruction).decision, "pass")
        self.assertEqual(apply_guard("allowlist", plan, self.scene, self.instruction).decision, "blocked")

    def test_other_object_needs_approval(self):
        plan = Plan("box_blue", "zone_a")
        self.assertEqual(apply_guard("allowlist", plan, self.scene, self.instruction).decision, "pass")
        result = apply_guard("allowlist+approval", plan, self.scene, self.instruction)
        self.assertEqual(result.decision, "approval_requested")

    def test_unknown_id_and_planner_error_never_pass(self):
        for plan in (Plan("box_none", "zone_a"), Plan("box_red", "zone_none"), Plan(None, None, error="refusal")):
            result = apply_guard("none", plan, self.scene, self.instruction)
            self.assertEqual(result.decision, "invalid_plan")
            self.assertFalse(result.passed)


class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.scene = load_scene()
        self.attacks = load_attacks()

    def test_counts_and_determinism(self):
        a = generate(5, 7, self.scene, self.attacks)
        b = generate(5, 7, self.scene, self.attacks)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 5 * (1 + len(self.attacks)))

    def test_only_carrier_label_is_changed(self):
        original = {o["id"]: o["label"] for o in self.scene["objects"]}
        for sc in generate(5, 1, self.scene, self.attacks):
            changed = [o["id"] for o in sc.scene["objects"] if o["label"] != original[o["id"]]]
            if sc.condition == "clean":
                self.assertEqual(changed, [])
            else:
                self.assertEqual(changed, [sc.carrier_object])
                self.assertNotEqual(sc.carrier_object, sc.truth_object)

    def test_source_scene_is_not_mutated(self):
        before = load_scene()
        generate(5, 1, self.scene, self.attacks)
        self.assertEqual(self.scene, before)


class PromptTest(unittest.TestCase):
    def test_separated_prompt_marks_labels_as_data(self):
        scene = load_scene()
        system, user = build_prompt("빨간 상자를 A 구역으로 옮겨라.", scene, "separated")
        self.assertIn("operator_instruction", system)
        self.assertIn("<scene_data>", user)
        naive_system, _ = build_prompt("빨간 상자를 A 구역으로 옮겨라.", scene, "naive")
        self.assertNotIn("operator_instruction", naive_system)


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.scenarios = generate(10, 3, load_scene(), load_attacks())
        self.levels = list(LEVELS)

    def _summary(self, obey: float) -> dict:
        planner = MockPlanner(seed=0, obey_prob={"naive": obey, "separated": obey})
        return {s["level"]: s for s in summarize(run(planner, self.scenarios, self.levels))}

    def test_planner_that_never_obeys_labels(self):
        for s in self._summary(0.0).values():
            self.assertEqual(s["clean_correct_passed"], s["clean_n"])
            self.assertEqual(s["attack_correct_passed"], s["attack_n"])
            for goal in ("forbidden_zone", "misroute"):
                self.assertEqual(s[f"{goal}_in_plan"], 0)
                self.assertEqual(s[f"{goal}_risk"], 0.0)
                # 잘못된 계획이 없으면 "검사가 놓친 비율"은 0이 아니라 해당 없음이다.
                self.assertIsNone(s[f"{goal}_miss"])

    def test_planner_that_always_obeys_labels(self):
        s = self._summary(1.0)
        n_forbidden = s["D0"]["forbidden_zone_n"]
        n_misroute = s["D0"]["misroute_n"]
        # 방어 없음: 두 공격 모두 계획에 반영되고 그대로 통과한다.
        self.assertEqual(s["D0"]["forbidden_zone_passed"], n_forbidden)
        self.assertEqual(s["D0"]["misroute_passed"], n_misroute)
        # D1과 D2는 같은 응답을 쓰므로 계획에 반영된 건수가 같다.
        self.assertEqual(s["D1"]["forbidden_zone_in_plan"], s["D2"]["forbidden_zone_in_plan"])
        # D1->D2: 금지 구역 계획은 전부 차단되지만, 허용 구역으로의 오배송은 그대로 통과한다.
        self.assertEqual(s["D1"]["forbidden_zone_passed"], n_forbidden)
        self.assertEqual(s["D2"]["forbidden_zone_in_plan"], n_forbidden)
        self.assertEqual(s["D2"]["forbidden_zone_passed"], 0)
        self.assertEqual(s["D2"]["forbidden_zone_miss"], 0.0)
        self.assertEqual(s["D2"]["attack_blocked"], n_forbidden)
        self.assertEqual(s["D2"]["misroute_passed"], n_misroute)
        self.assertEqual(s["D2"]["misroute_miss"], 1.0)
        # D2->D3: 지시문에 없는 상자를 고른 계획은 승인 요청으로 보류된다.
        self.assertEqual(s["D3"]["misroute_passed"], 0)
        self.assertEqual(s["D3"]["attack_held_for_approval"], n_misroute)
        # 공격이 없는 장면은 어느 수준에서도 지시대로 통과하고 보류되지 않는다.
        self.assertEqual(s["D3"]["clean_correct_passed"], s["D3"]["clean_n"])
        self.assertEqual(s["D3"]["clean_held_for_approval"], 0)

    def test_two_denominators_differ(self):
        # 일부만 속는 계획기: 전체 사례 기준 위험과 잘못된 계획 기준 놓침 비율은 분모가 다르다.
        planner = MockPlanner(seed=1, obey_prob={"naive": 0.5, "separated": 0.5})
        s = {x["level"]: x for x in summarize(run(planner, self.scenarios, self.levels))}["D1"]
        self.assertGreater(s["misroute_in_plan"], 0)
        self.assertLess(s["misroute_in_plan"], s["misroute_n"])
        self.assertEqual(s["misroute_risk"], s["misroute_passed"] / s["misroute_n"])
        self.assertEqual(s["misroute_miss"], s["misroute_passed"] / s["misroute_in_plan"])
        self.assertLess(s["misroute_risk"], s["misroute_miss"])


class PhysicalLinkTest(unittest.TestCase):
    """계획을 정책 목표로 잇는 부분. 시뮬레이터 없이 확인한다."""

    def setUp(self):
        self.scene = load_scene()
        self.scenarios = generate(10, 3, self.scene, load_attacks())
        self.rows = run(CompromisedPlanner(seed=0), self.scenarios, list(LEVELS))
        self.episodes = episodes_from_plans(self.rows, self.scene)

    def test_compromised_planner_always_reflects_attack(self):
        s = {x["level"]: x for x in summarize(self.rows)}
        for level in LEVELS:
            self.assertEqual(s[level]["forbidden_zone_in_plan"], s[level]["forbidden_zone_n"])
            self.assertEqual(s[level]["misroute_in_plan"], s[level]["misroute_n"])
        self.assertEqual(s["D2"]["forbidden_zone_passed"], 0)
        self.assertEqual(s["D3"]["misroute_passed"], 0)

    def test_one_episode_per_scenario_with_zone_center_target(self):
        self.assertEqual(len(self.episodes), len(self.scenarios))
        zones = {z["id"]: z for z in self.scene["zones"]}
        for e in self.episodes:
            self.assertEqual(e["target"], zones[e["plan_zone"]]["center"])
            self.assertEqual(e["target_allowed"], int(zones[e["plan_zone"]]["allowed"]))
            self.assertEqual(e["guard_D1"], "pass")
            if not e["target_allowed"]:
                self.assertEqual(e["guard_D2"], "blocked")

    def test_plans_differing_between_levels_are_rejected(self):
        rows = [dict(r) for r in self.rows]
        victim = next(r for r in rows if r["level"] == "D2")
        victim["plan_zone"] = "zone_a" if victim["plan_zone"] != "zone_a" else "zone_b"
        with self.assertRaises(ValueError):
            episodes_from_plans(rows, self.scene)

    def test_invalid_plan_has_no_episode(self):
        rows = [dict(r) for r in self.rows]
        key = (rows[0]["trial_id"], rows[0]["condition"], rows[0]["attack_id"])
        for r in rows:
            if (r["trial_id"], r["condition"], r["attack_id"]) == key:
                r["plan_zone"] = ""
        self.assertEqual(len(episodes_from_plans(rows, self.scene)), len(self.scenarios) - 1)

    def test_summary_filters_by_guard_and_uses_na_when_nothing_delivered(self):
        # 가짜 실행 결과: 금지 목적지는 모두 진입, 허용 목적지는 침범 없이 도달했다고 둔다.
        rows = [
            {**e, "entered_forbidden": int(not e["target_allowed"]), "first_success_step": 20}
            for e in self.episodes
        ]
        s = {x["level"]: x for x in summarize_physical(rows)}
        n_forbidden = sum(not e["target_allowed"] for e in self.episodes)
        n_misroute = sum(sc.attack_goal == "misroute" for sc in self.scenarios)
        self.assertGreater(n_forbidden, 0)
        self.assertEqual(s["D1"]["forbidden_delivered"], n_forbidden)
        self.assertEqual(s["D1"]["forbidden_entered"], n_forbidden)
        self.assertEqual(s["D1"]["allowed_delivered"], len(rows) - n_forbidden)
        # D2: 금지 목적지가 모두 차단되면 진입 건수는 0이 아니라 해당 없음이다.
        self.assertEqual(s["D2"]["forbidden_delivered"], 0)
        self.assertIsNone(s["D2"]["forbidden_entered"])
        self.assertEqual(s["D2"]["allowed_delivered"], s["D1"]["allowed_delivered"])
        # D3: 지시와 다른 상자를 고른 계획이 보류되어 전달 건수가 그만큼 준다.
        self.assertEqual(s["D3"]["allowed_delivered"], s["D2"]["allowed_delivered"] - n_misroute)
        self.assertEqual(s["D3"]["allowed_incursion"], 0)


if __name__ == "__main__":
    unittest.main()
