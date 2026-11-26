"""여유 벌점 과제(M2)의 기하와 집계 점검. 시뮬레이터 없이 돈다.

sim/rlguard_tasks의 텐서 식은 torch와 Isaac Lab이 필요해 여기서 부르지 않는다. 같은 식을
robotguard.zones.distance_to_zone으로 계산해, 문서에 적은 값(4cm 아래 목표의 벌점 등)을 확인한다.
"""

import unittest

from robotguard import seeds
from robotguard.scenarios import load_scene
from robotguard.zones import distance_to_zone

MARGIN = 0.05


def margin_term(point, zone):
    return min(max((MARGIN - distance_to_zone(point, zone)) / MARGIN, 0.0), 1.0)


class MarginGeometryTest(unittest.TestCase):
    def setUp(self):
        zones = {z["id"]: z for z in load_scene()["zones"]}
        self.x, self.b = zones["zone_x"], zones["zone_b"]

    def test_term_is_one_inside_and_zero_beyond_margin(self):
        self.assertEqual(margin_term(self.x["center"], self.x), 1.0)
        cx, cy, cz = self.x["center"]
        self.assertEqual(margin_term([cx, cy, cz - 0.05 - 0.06], self.x), 0.0)

    def test_probe_below_target_carries_part_of_the_penalty(self):
        cx, cy, cz = self.x["center"]
        probe = [cx, cy, cz - self.x["half_size"][2] - 0.04]  # eval_policy.py의 probe_below
        self.assertAlmostEqual(margin_term(probe, self.x), 0.2, places=6)
        # 1cm 더 아래는 벌점이 없고 목표의 성공 반경(0.05m) 안이다.
        self.assertAlmostEqual(margin_term([cx, cy, probe[2] - 0.01], self.x), 0.0, places=6)

    def test_zone_b_center_is_outside_margin(self):
        self.assertAlmostEqual(distance_to_zone(self.b["center"], self.x), 0.10, places=6)
        self.assertEqual(margin_term(self.b["center"], self.x), 0.0)
        # 구역 B 상자의 X 쪽 면은 X 상자에서 정확히 5cm라, B 상자 안에서는 벌점이 없다.
        bx, by, bz = self.b["center"]
        self.assertAlmostEqual(margin_term([bx, by + self.b["half_size"][1], bz], self.x), 0.0, places=6)


def _row(policy, name, entered=0, success=10, final=0.02, min_err=0.01, dist=0.2):
    return {"policy": policy, "target_name": name, "entered_forbidden": str(entered),
            "first_success_step": str(success), "final_pos_err": str(final), "min_pos_err": str(min_err),
            "target_dist_to_forbidden": str(dist)}


class MarginSummaryTest(unittest.TestCase):
    def test_default_conditions_unchanged(self):
        self.assertEqual(seeds.CONDITIONS, ["safe_w0", "safe_w2"])

    def test_near_cells_counts_subsets(self):
        rows = [_row("safe_m2", "probe_below", entered=1), _row("safe_m2", "probe_below", success=-1),
                _row("safe_m2", "random_allowed", dist=0.06), _row("safe_m2", "random_allowed", dist=0.3),
                _row("safe_m2", "zone_b", success=30), _row("safe_m2", "zone_x", success=-1, min_err=0.15)]
        cells = seeds.near_cells(rows)
        self.assertEqual(cells[0], "1/2")   # 4cm 아래 침범
        self.assertEqual(cells[1], "1/2")   # 4cm 아래 도달
        self.assertEqual(cells[3], "0/1")   # 구역까지 0.10m 미만 무작위 허용 목표는 1개
        self.assertEqual(cells[6], "30")
        self.assertEqual(cells[8], "0.150")

    def test_margin_condition_groups_by_seed(self):
        self.assertEqual(seeds.split_name("safe_m2"), ("safe_m2", 42))
        self.assertEqual(seeds.split_name("safe_m2_s3"), ("safe_m2", 3))


if __name__ == "__main__":
    unittest.main()
