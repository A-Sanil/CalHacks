from sim_realtime import run_simulation

def test_realtime_holds_invariants_long_run():
    stats = run_simulation(ticks=400, seed=7, solve_every=20)
    assert stats["solves"] == 20
    assert stats["cache"]["hit_rate_pct"] > 0      # paraphrases got cached
    assert stats["cache"]["tokens_saved"] > 0
    assert stats["last_total_cost"] is not None and stats["last_total_cost"] >= 0

def test_realtime_multiple_seeds():
    for seed in (1, 2, 3, 99):
        stats = run_simulation(ticks=200, seed=seed, solve_every=25)
        assert stats["solves"] == 8
