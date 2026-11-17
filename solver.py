"""Exact minimum set cover using only the Python standard library.

The minimum is proved before any limit on the number of returned solutions is
applied. Dimensions with equal or contained ore sets are deliberately retained,
because they can participate in different, equally small covers.
"""

from __future__ import annotations

from functools import lru_cache


def solve_cover(
    dimension_ores: dict[str, set[str]],
    required_ores: set[str],
    *,
    max_solutions: int = 20,
) -> dict:
    """Find the fewest dimensions covering every required ore, exactly.

    ``max_solutions=0`` returns every optimum; otherwise at most that many are
    returned. ``solutions_truncated`` is true only after another optimum has
    actually been found. An unavailable required ore makes the result infeasible;
    the function never silently reduces ``required_ores``.

    For an uncovered ore, every cover must choose at least one of its providers.
    The memoized recurrence tries those choices and removes all ores covered by
    the chosen dimension. Greedy covers are upper bounds only. Counting and
    disjoint-provider bounds can terminate a state only when they prove its
    optimum. A separate search enumerates covers of the proved minimum size.
    """
    if not isinstance(max_solutions, int) or max_solutions < 0:
        raise ValueError("max_solutions must be a nonnegative integer (0 means all)")

    names = list(dimension_ores)
    ores = sorted(required_ores)
    ore_index = {ore: i for i, ore in enumerate(ores)}
    masks = [
        sum(1 << ore_index[ore] for ore in dimension_ores[name] if ore in ore_index)
        for name in names
    ]
    providers = [0] * len(ores)
    for dimension, mask in enumerate(masks):
        remaining = mask
        while remaining:
            bit = remaining & -remaining
            providers[bit.bit_length() - 1] |= 1 << dimension
            remaining ^= bit

    missing = [ores[i] for i, choices in enumerate(providers) if not choices]
    forced_by_ores: dict[str, list[str]] = {}
    forced_mask = 0
    for ore, choices in zip(ores, providers):
        if choices and choices & (choices - 1) == 0:
            forced_mask |= choices
            name = names[choices.bit_length() - 1]
            forced_by_ores.setdefault(name, []).append(ore)
    forced_indices = [i for i in range(len(names)) if forced_mask & (1 << i)]
    forced_names = [names[i] for i in forced_indices]
    result = {
        "feasible": not missing,
        "minimum_count": None,
        "minimum_proven": False,
        "solutions": [],
        "solutions_truncated": False,
        "optimal_solution_count": None,
        "forced_dimensions": forced_names,
        "forced_by_ores": {name: forced_by_ores[name] for name in forced_names},
        "uncovered_ores": missing,
        "required_ore_count": len(ores),
        "dimension_count": len(names),
        "minimum_search_states": 0,
        "enumeration_nodes": 0,
    }
    if missing:
        return result

    uncovered = (1 << len(ores)) - 1
    for i in forced_indices:
        uncovered &= ~masks[i]
    active = [i for i, mask in enumerate(masks) if mask & uncovered]
    rare_order = sorted(range(len(ores)), key=lambda i: (providers[i].bit_count(), i))

    def lower_bound(remaining: int) -> int:
        if not remaining:
            return 0
        maximum_gain = max((masks[i] & remaining).bit_count() for i in active)
        count_bound = (remaining.bit_count() + maximum_gain - 1) // maximum_gain
        # Ores with pairwise disjoint provider sets need different dimensions.
        used_providers = 0
        packing_bound = 0
        for ore in rare_order:
            if remaining & (1 << ore) and not (providers[ore] & used_providers):
                packing_bound += 1
                used_providers |= providers[ore]
        return max(count_bound, packing_bound)

    def greedy_count(remaining: int) -> int:
        count = 0
        while remaining:
            dimension = max(active, key=lambda i: (masks[i] & remaining).bit_count())
            remaining &= ~masks[dimension]
            count += 1
        return count

    @lru_cache(maxsize=None)
    def minimum(remaining: int) -> int:
        if not remaining:
            return 0
        bound = lower_bound(remaining)
        best = greedy_count(remaining)
        if best == bound:
            return best
        ore = next(i for i in rare_order if remaining & (1 << i))
        options = [i for i in active if providers[ore] & (1 << i)]
        options.sort(key=lambda i: (-(masks[i] & remaining).bit_count(), i))
        for dimension in options:
            rest = remaining & ~masks[dimension]
            if 1 + lower_bound(rest) >= best:
                continue
            best = min(best, 1 + minimum(rest))
            if best == bound:
                break
        return best

    additional_count = minimum(uncovered)
    solutions: list[list[str]] = []
    stop_after = max_solutions + 1 if max_solutions else None
    enumeration_nodes = 0

    def enumerate_optima(remaining: int, allowed: int, chosen: int, slots: int) -> bool:
        """Return true only when the requested solution cap has been exceeded."""
        nonlocal enumeration_nodes
        enumeration_nodes += 1
        if not remaining:
            if slots == 0:
                picked = chosen | forced_mask
                solutions.append([name for i, name in enumerate(names) if picked & (1 << i)])
            return stop_after is not None and len(solutions) >= stop_after
        if slots <= 0 or allowed.bit_count() < slots or minimum(remaining) > slots:
            return False

        fewest_choices = None
        fewest_count = len(names) + 1
        useful = 0
        for ore in rare_order:
            if remaining & (1 << ore):
                choices = providers[ore] & allowed
                count = choices.bit_count()
                if not count:
                    return False
                useful |= choices
                if count < fewest_count:
                    fewest_count = count
                    fewest_choices = choices
        allowed &= useful
        options = [i for i in active if fewest_choices & (1 << i)]
        options.sort(key=lambda i: (-(masks[i] & remaining).bit_count(), i))
        # Partition covers by their first selected provider of the chosen ore.
        # Later branches exclude earlier providers, preventing duplicate covers.
        for dimension in options:
            bit = 1 << dimension
            allowed &= ~bit
            if enumerate_optima(
                remaining & ~masks[dimension], allowed, chosen | bit, slots - 1
            ):
                return True
        return False

    enumerate_optima(uncovered, sum(1 << i for i in active), 0, additional_count)
    truncated = bool(max_solutions and len(solutions) > max_solutions)
    result.update(
        minimum_count=len(forced_indices) + additional_count,
        minimum_proven=True,
        solutions=solutions[:max_solutions] if truncated else solutions,
        solutions_truncated=truncated,
        optimal_solution_count=None if truncated else len(solutions),
        minimum_search_states=minimum.cache_info().currsize,
        enumeration_nodes=enumeration_nodes,
    )
    return result
