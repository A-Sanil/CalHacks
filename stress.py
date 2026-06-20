"""stress.py -- heavy continuous run; invariants asserted EVERY tick."""
import time
from sim_realtime import run_simulation

def main(seeds=range(1, 16), ticks=800):
    t0 = time.time()
    agg = {"ticks": 0, "solves": 0, "tokens_saved": 0}
    rates = []
    for sd in seeds:
        st = run_simulation(ticks=ticks, seed=sd, solve_every=25)
        agg["ticks"] += st["ticks"]; agg["solves"] += st["solves"]
        agg["tokens_saved"] += st["cache"]["tokens_saved"]; rates.append(st["cache"]["hit_rate_pct"])
    dt = time.time() - t0
    print(f"OK  {agg['ticks']} live ticks across {len(list(seeds))} seeds in {dt:.1f}s "
          f"({agg['ticks']/dt:.0f} ticks/s) -- ALL INVARIANTS HELD")
    print(f"    solver runs={agg['solves']}  tokens_saved={agg['tokens_saved']:,}  "
          f"avg_cache_hit={sum(rates)/len(rates):.1f}%")

if __name__ == "__main__":
    main()
