from core.math500 import load_math500


def test_math500_mock_sample_is_deterministic_and_stratified():
    first = load_math500(n=17, seed=42, offline_mock=True)
    second = load_math500(n=17, seed=42, offline_mock=True)
    assert [problem.problem_id for problem in first] == [problem.problem_id for problem in second]
    counts = {level: sum(problem.level == level for problem in first) for level in range(1, 6)}
    assert max(counts.values()) - min(counts.values()) <= 1
    assert all(problem.problem and problem.solution and problem.answer and problem.subject for problem in first)
