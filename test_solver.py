"""Compare the exact solver with an independent exhaustive reference search."""

from itertools import combinations
import random
import unittest

from solver import solve_cover


def brute_force(dimension_ores, required_ores):
    names = list(dimension_ores)
    for count in range(len(names) + 1):
        found = set()
        for chosen in combinations(names, count):
            covered = set().union(*(dimension_ores[name] for name in chosen))
            if required_ores <= covered:
                found.add(frozenset(chosen))
        if found:
            return count, found
    return None, set()


class ExactCoverTests(unittest.TestCase):
    def check_against_brute_force(self, dimensions, ores):
        expected_count, expected_solutions = brute_force(dimensions, ores)
        result = solve_cover(dimensions, ores, max_solutions=0)
        self.assertEqual(result["feasible"], expected_count is not None)
        self.assertEqual(result["minimum_count"], expected_count)
        actual = [frozenset(solution) for solution in result["solutions"]]
        self.assertEqual(set(actual), expected_solutions)
        self.assertEqual(len(actual), len(set(actual)), "duplicate solution")
        self.assertFalse(result["solutions_truncated"])
        if expected_count is not None:
            self.assertTrue(result["minimum_proven"])
            self.assertEqual(result["optimal_solution_count"], len(expected_solutions))
        for cap in (1, 2, len(expected_solutions)):
            limited = solve_cover(dimensions, ores, max_solutions=cap)
            self.assertEqual(limited["minimum_count"], expected_count)
            self.assertEqual(limited["solutions_truncated"], bool(cap and len(expected_solutions) > cap))
            self.assertEqual(len(limited["solutions"]), min(cap, len(expected_solutions)) if cap else len(expected_solutions))
            self.assertTrue(all(frozenset(s) in expected_solutions for s in limited["solutions"]))

    def test_greedy_is_not_the_answer(self):
        dimensions = {
            "largest": {"1", "2", "3", "4"},
            "left": {"1", "2", "5"},
            "right": {"3", "4", "6"},
            "five": {"5"},
            "six": {"6"},
        }
        result = solve_cover(dimensions, set("123456"), max_solutions=0)
        self.assertEqual(result["minimum_count"], 2)
        self.assertEqual(result["solutions"], [["left", "right"]])

    def test_equal_and_dominated_dimensions_keep_ties(self):
        self.check_against_brute_force(
            {"A": {"x"}, "B": {"x", "y"}, "C": {"y", "z"}},
            {"x", "y", "z"},
        )
        self.check_against_brute_force(
            {"A": {"x"}, "B": {"x"}, "C": {"y"}, "D": {"y"}},
            {"x", "y"},
        )

    def test_missing_ore_is_not_silently_dropped(self):
        result = solve_cover({"planet": {"available"}}, {"available", "missing"})
        self.assertFalse(result["feasible"])
        self.assertIsNone(result["minimum_count"])
        self.assertEqual(result["uncovered_ores"], ["missing"])
        self.assertEqual(result["solutions"], [])

    def test_forced_witnesses_and_irrelevant_ores(self):
        result = solve_cover({"A": {"x", "extra"}, "B": {"y"}}, {"x", "y"})
        self.assertEqual(result["forced_dimensions"], ["A", "B"])
        self.assertEqual(result["forced_by_ores"], {"A": ["x"], "B": ["y"]})
        self.assertEqual(result["solutions"], [["A", "B"]])

    def test_empty_cases(self):
        self.check_against_brute_force({}, set())
        self.check_against_brute_force({"unused": {"extra"}}, set())
        self.check_against_brute_force({}, {"missing"})

    def test_seeded_random_instances(self):
        rng = random.Random(2048)
        for case in range(400):
            ores = {str(i) for i in range(rng.randrange(10))}
            dimensions = {
                f"D{i}": {ore for ore in sorted(ores) if rng.random() < 0.45}
                for i in range(rng.randrange(9))
            }
            with self.subTest(case=case):
                self.check_against_brute_force(dimensions, ores)

    def test_invalid_solution_cap(self):
        for cap in (-1, 1.5, "all"):
            with self.assertRaises(ValueError):
                solve_cover({}, set(), max_solutions=cap)


if __name__ == "__main__":
    unittest.main()
