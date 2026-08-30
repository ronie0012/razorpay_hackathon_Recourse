"""Deterministic 10k-event ingress micro-benchmark for the production proof screen."""
from __future__ import annotations

import hashlib
import hmac
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNT = 10_000
UNIQUE = 1_000
SECRET = b"load-test-only-secret"


def main() -> None:
    seen: set[str] = set()
    latencies = []
    accepted = duplicates = 0
    started = time.perf_counter()
    for index in range(COUNT):
        event_id = f"evt_{index % UNIQUE:04d}"
        body = json.dumps({"event": "payment.failed", "id": event_id}, separators=(",", ":")).encode()
        signature = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        tick = time.perf_counter_ns()
        verified = hmac.compare_digest(hmac.new(SECRET, body, hashlib.sha256).hexdigest(), signature)
        if verified and event_id not in seen:
            seen.add(event_id)
            accepted += 1
        else:
            duplicates += 1
        latencies.append((time.perf_counter_ns() - tick) / 1_000_000)
    elapsed = time.perf_counter() - started
    ordered = sorted(latencies)
    artifact = {
        "label": "LOCAL SYNTHETIC INGRESS MICRO-BENCHMARK — NOT A CAPACITY PROMISE",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "event_count": COUNT,
        "unique_event_count": UNIQUE,
        "duplicate_event_count": duplicates,
        "duplicate_suppression_rate": duplicates / (COUNT - UNIQUE),
        "accepted_once_rate": accepted / UNIQUE,
        "throughput_events_per_second": round(COUNT / elapsed, 1),
        "p50_latency_ms": round(statistics.median(latencies), 4),
        "p95_latency_ms": round(ordered[int(len(ordered) * .95) - 1], 4),
        "estimated_compute_cost_usd": 0,
        "scope": "HMAC verification plus in-memory event-id deduplication; excludes network and durable database I/O",
    }
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
    artifact["run_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    output = ROOT / "evals" / "results" / "load-test.json"
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2))


if __name__ == "__main__":
    main()
