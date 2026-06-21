"""Replay normalized Palisades events into Redis as a deterministic stream."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "data" / "processed" / "palisades" / "replay_timeline.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between replay events")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fakeredis", action="store_true", help="Validate Redis operations in memory")
    args = parser.parse_args()
    events = json.loads(TIMELINE.read_text(encoding="utf-8"))
    client = None
    if args.fakeredis:
        import fakeredis
        client = fakeredis.FakeRedis(decode_responses=True)
    elif not args.dry_run:
        import redis
        client = redis.Redis.from_url(args.redis_url, decode_responses=True)
        client.ping()

    for sequence, event in enumerate(events):
        envelope = {"sequence": sequence, **event}
        print(f"[{sequence:02d}] {event['timestamp']} {event['type']} ({event['source']})")
        if client is not None:
            payload = json.dumps(envelope, separators=(",", ":"))
            client.xadd("aegis:events", {"type": event["type"], "timestamp": event["timestamp"], "payload": payload})
            client.set(f"aegis:state:{event['type']}", payload)
            client.publish("aegis:updates", payload)
        if sequence < len(events) - 1: time.sleep(args.interval)
    if client is not None:
        print(f"Redis validation: {client.xlen('aegis:events')} stream entries")
        print(f"Current state keys: {sorted(key for key in client.scan_iter('aegis:state:*'))}")


if __name__ == "__main__":
    main()
