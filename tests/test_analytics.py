"""통계 함수 점검. 실행: python -m unittest discover -s tests -v

윌슨 구간, 뉴컴 차이 구간, 시드 순열 검정은 표준 라이브러리만 쓴다.
클로퍼-피어슨 구간은 scipy가 있을 때만 확인한다.
"""

import importlib.util
import unittest

from robotguard.analytics import clopper_pearson, newcombe_diff, rank_biserial, seed_permutation_mwu, wilson

HAS_SCIPY = importlib.util.find_spec("scipy") is not None


class IntervalTest(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = wilson(0, 256)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.01478, places=4)
        lo, hi = wilson(168, 256)
        self.assertAlmostEqual(lo, 0.5961, places=3)
        self.assertAlmostEqual(hi, 0.7117, places=3)

    def test_wilson_contains_rate(self):
        for k, n in [(1, 10), (5, 60), (59, 60), (60, 60)]:
            lo, hi = wilson(k, n)
            self.assertLessEqual(lo, k / n)
            self.assertGreaterEqual(hi, k / n)

    def test_newcombe_zero_vs_zero_is_symmetric(self):
        d, lo, hi = newcombe_diff(0, 240, 0, 240)
        self.assertEqual(d, 0.0)
        self.assertAlmostEqual(lo, -hi)

    @unittest.skipUnless(HAS_SCIPY, "scipy 없음")
    def test_clopper_pearson_zero_successes(self):
        lo, hi = clopper_pearson(0, 80)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** (1 / 80), places=6)  # k=0이면 닫힌 꼴


class SeedTestTest(unittest.TestCase):
    def test_minimum_p_for_four_vs_four(self):
        _, p = seed_permutation_mwu([0.9, 0.8, 0.7, 0.6], [0.0, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(p, 2 / 70)

    def test_identical_groups_give_p_one(self):
        u, p = seed_permutation_mwu([0.0] * 4, [0.0] * 4)
        self.assertEqual(p, 1.0)
        self.assertEqual(rank_biserial(u, 4, 4), 0.0)

    def test_rank_biserial_range(self):
        u, _ = seed_permutation_mwu([1, 2, 3, 4], [5, 6, 7, 8])
        self.assertEqual(rank_biserial(u, 4, 4), -1.0)


if __name__ == "__main__":
    unittest.main()
