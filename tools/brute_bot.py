#!/usr/bin/env python3
"""brute_bot.py — the gate test for throw.dog threat #1 (code brute-forcing).

This is a TEST TOOL, not shipped code. It does not go in the Docker image or
requirements. It attacks a *running* throw.dog instance by guessing codes drawn
from the real code space, to prove the defensive gate (per-IP miss budget +
global miss flood tarpit, see app/gatekeeper.py and model/11-security-abuse.md)
actually holds: over several TTL windows a scraper must retrieve ZERO planted
throws while an honest reader still gets through.

The read endpoint is ``POST /api/throws/{code}``: 200 + {"text": ...} on a hit,
a byte-identical slow 404 on every kind of miss.

Two attack modes
----------------
* ``single-ip``  — hammer the read endpoint as fast as one source allows.
* ``botnet``     — imitate many distinct client IPs from one machine, using the
                   trusted-proxy forwarding header the app honours
                   (``X-Forwarded-For`` / ``CF-Connecting-IP``). This ONLY moves
                   the per-IP budget when the target is configured with
                   ``THROW_TRUSTED_PROXY=1`` — i.e. a test harness you control,
                   NEVER production. Against a directly-exposed prod app the
                   header is ignored and every guess is charged to your one real
                   socket IP, so botnet degenerates into single-ip.

Running it against a local instance
-----------------------------------
Start a target that trusts the forwarding header (test harness only)::

    THROW_TRUSTED_PROXY=1 THROW_MISS_DELAY_MS=200 \
        .venv/bin/uvicorn app.main:app --port 8000

Then, from the repo root::

    # quick single-IP smoke run
    .venv/bin/python tools/brute_bot.py --target http://127.0.0.1:8000 \
        --mode single-ip --duration 5 --concurrency 20

    # botnet with 100 imitated IPs
    .venv/bin/python tools/brute_bot.py --target http://127.0.0.1:8000 \
        --mode botnet --ips 100 --duration 30 --concurrency 50

    # the actual gate check: plant throws, attack, verify none were pulled AND
    # an honest read still works — prints PASS / FAIL
    .venv/bin/python tools/brute_bot.py --target http://127.0.0.1:8000 \
        --mode botnet --ips 100 --plant 5 --windows 3 --duration 20

The live-deployment gate run against the real throw.dog server is a MANUAL,
human-in-the-loop founder step. This script only builds and exercises the tool;
pointing it at production is a deliberate operator decision, not automation.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import random
import sys
import time
from dataclasses import dataclass, field

import httpx

# Draw guesses from the *real* code space so this is a realistic attack, not
# random noise. Import the shipped wordlists; fall back to a path insert when
# run from inside tools/.
try:
    from app.codewords import ADJECTIVES, COMBINATIONS, NOUNS, SEPARATOR
except ModuleNotFoundError:  # pragma: no cover - convenience for odd cwds
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.codewords import ADJECTIVES, COMBINATIONS, NOUNS, SEPARATOR


# --------------------------------------------------------------------------- #
# Result accounting
# --------------------------------------------------------------------------- #
@dataclass
class AttackStats:
    """What the run observed. Shared, mutated by the worker coroutines."""

    attempts: int = 0
    hits: int = 0
    misses: int = 0  # ordinary 404
    throttled: int = 0  # 429 / 503 — explicit back-pressure
    slow_misses: int = 0  # 404s that took >= slow_threshold seconds (tarpit)
    errors: int = 0  # transport failures
    tried: set[str] = field(default_factory=set)
    hit_codes: set[str] = field(default_factory=set)
    total_latency: float = 0.0

    def coverage_fraction(self) -> float:
        return len(self.tried) / COMBINATIONS if COMBINATIONS else 0.0


# --------------------------------------------------------------------------- #
# Guess generation
# --------------------------------------------------------------------------- #
def random_code() -> str:
    """A single guess from the real Cartesian code space."""
    return f"{random.choice(ADJECTIVES)}{SEPARATOR}{random.choice(NOUNS)}"


def synth_ip(index: int) -> str:
    """A deterministic, well-formed public-ish IPv4 for imitated client #index.

    Spread across 10.x so each worker presents a distinct forwarded address;
    the app charges the per-IP budget to whatever this header carries when it
    trusts the proxy.
    """
    return str(ipaddress.IPv4Address(0x0A000000 + (index % 0x00FFFFFF) + 1))


# --------------------------------------------------------------------------- #
# The attack
# --------------------------------------------------------------------------- #
async def _worker(
    client: httpx.AsyncClient,
    base: str,
    stats: AttackStats,
    deadline: float,
    max_attempts: int,
    header_name: str | None,
    ip_pool: list[str] | None,
    slow_threshold: float,
    stop: asyncio.Event,
) -> None:
    """One concurrent guesser. Loops until time or attempt budget runs out."""
    while not stop.is_set():
        if time.monotonic() >= deadline:
            break
        if max_attempts and stats.attempts >= max_attempts:
            break

        code = random_code()
        headers = {}
        if header_name and ip_pool:
            headers[header_name] = random.choice(ip_pool)

        started = time.monotonic()
        try:
            resp = await client.post(f"{base}/api/throws/{code}", headers=headers)
        except httpx.HTTPError:
            stats.errors += 1
            continue
        elapsed = time.monotonic() - started

        stats.attempts += 1
        stats.tried.add(code)
        stats.total_latency += elapsed

        if resp.status_code == 200:
            stats.hits += 1
            stats.hit_codes.add(code)
        elif resp.status_code in (429, 503):
            stats.throttled += 1
        else:  # 404 and anything else counts as a miss
            stats.misses += 1
            if elapsed >= slow_threshold:
                stats.slow_misses += 1


async def run_attack(
    base: str,
    *,
    mode: str,
    ips: int,
    duration: float,
    max_attempts: int,
    concurrency: int,
    slow_threshold: float,
    timeout: float,
    header_name: str,
    stats: AttackStats | None = None,
) -> AttackStats:
    """Drive ``concurrency`` guessers against ``base`` for ``duration`` seconds."""
    stats = stats if stats is not None else AttackStats()
    ip_pool: list[str] | None = None
    effective_header: str | None = None
    if mode == "botnet":
        ip_pool = [synth_ip(i) for i in range(max(1, ips))]
        effective_header = header_name

    deadline = time.monotonic() + duration if duration else float("inf")
    stop = asyncio.Event()
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        workers = [
            asyncio.create_task(
                _worker(
                    client, base, stats, deadline, max_attempts,
                    effective_header, ip_pool, slow_threshold, stop,
                )
            )
            for _ in range(max(1, concurrency))
        ]
        try:
            await asyncio.gather(*workers)
        finally:
            stop.set()
    return stats


# --------------------------------------------------------------------------- #
# Gate check: plant, attack, verify
# --------------------------------------------------------------------------- #
async def plant_throws(base: str, count: int, timeout: float) -> list[tuple[str, str]]:
    """Create ``count`` throws via the API. Returns [(code, secret_text), ...]."""
    planted: list[tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i in range(count):
            secret = f"planted-secret-{i}-{random.randint(10**6, 10**7)}"
            resp = await client.post(f"{base}/api/throws", json={"text": secret})
            resp.raise_for_status()
            planted.append((resp.json()["code"], secret))
    return planted


async def honest_read(base: str, timeout: float) -> bool:
    """Plant a throw, then read it back through the front door. True on success.

    Runs during/after the attack to prove the tarpit does not kill an honest
    user. Uses no forwarded header, so it presents as a fresh legitimate client.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        secret = f"honest-{random.randint(10**6, 10**7)}"
        created = await client.post(f"{base}/api/throws", json={"text": secret})
        if created.status_code != 201:
            return False
        code = created.json()["code"]
        got = await client.post(f"{base}/api/throws/{code}")
        return got.status_code == 200 and got.json().get("text") == secret


async def run_gate_check(args: argparse.Namespace) -> int:
    """Plant → attack over several TTL windows → verify. Prints PASS/FAIL.

    Success criterion (model/11-security-abuse.md): across the windows the bot
    retrieves ZERO planted throws AND an honest read still succeeds under attack.
    """
    base = args.target.rstrip("/")
    print(f"[gate] planting {args.plant} throw(s) on {base} ...")
    planted = await plant_throws(base, args.plant, args.timeout)
    planted_codes = {code for code, _ in planted}
    print(f"[gate] planted codes (kept secret from the guesser): {len(planted_codes)}")

    agg = AttackStats()
    honest_ok = True
    for window in range(1, args.windows + 1):
        print(f"[gate] --- window {window}/{args.windows} "
              f"({args.duration:.0f}s of {args.mode}) ---")
        await run_attack(
            base,
            mode=args.mode,
            ips=args.ips,
            duration=args.duration,
            max_attempts=args.attempts,
            concurrency=args.concurrency,
            slow_threshold=args.slow_threshold,
            timeout=args.timeout,
            header_name=args.header,
            stats=agg,
        )
        ok = await honest_read(base, args.timeout)
        honest_ok = honest_ok and ok
        print(f"[gate]   honest read this window: {'OK' if ok else 'FAILED'}")

    stolen = agg.hit_codes & planted_codes
    print()
    print_report(agg, base, args)
    print()
    print(f"[gate] planted throws stolen by the bot: {len(stolen)} "
          f"{sorted(stolen) if stolen else ''}")
    print(f"[gate] honest reads survived the attack: {'YES' if honest_ok else 'NO'}")

    passed = not stolen and honest_ok
    print()
    print(f"[gate] RESULT: {'PASS — gate holds' if passed else 'FAIL — gate leaks'}")
    return 0 if passed else 1


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def print_report(stats: AttackStats, base: str, args: argparse.Namespace) -> None:
    distinct = len(stats.tried)
    cov = stats.coverage_fraction()
    avg_lat = (stats.total_latency / stats.attempts) if stats.attempts else 0.0
    non_hit = stats.attempts - stats.hits
    tarpit_share = (stats.slow_misses / non_hit) if non_hit else 0.0
    throttle_share = (stats.throttled / stats.attempts) if stats.attempts else 0.0

    print("=" * 60)
    print(f"target            : {base}")
    print(f"mode              : {args.mode}"
          + (f" ({args.ips} imitated IPs via {args.header})" if args.mode == "botnet" else ""))
    print(f"attempts made     : {stats.attempts}")
    print(f"distinct codes    : {distinct}")
    print(f"code space        : {COMBINATIONS}")
    print(f"coverage          : {cov * 100:.4f}%  ({distinct}/{COMBINATIONS})")
    print(f"hits (retrieved)  : {stats.hits}"
          + (f"  {sorted(stats.hit_codes)}" if stats.hit_codes else ""))
    print(f"plain misses      : {stats.misses}")
    print(f"slow/tarpit misses: {stats.slow_misses}  "
          f"({tarpit_share * 100:.1f}% of non-hits, >= {args.slow_threshold}s)")
    print(f"throttled (429/503): {stats.throttled}  ({throttle_share * 100:.1f}% of attempts)")
    print(f"transport errors  : {stats.errors}")
    print(f"avg latency       : {avg_lat * 1000:.0f} ms")
    print("=" * 60)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brute_bot.py",
        description=(
            "Gate test for throw.dog: brute-force the code space against a "
            "running instance and report how the rate-limit/tarpit defence holds."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "modes:\n"
            "  single-ip   hammer the read endpoint from one source, full speed\n"
            "  botnet      imitate many client IPs via the trusted-proxy header\n"
            "              (only bites when target has THROW_TRUSTED_PROXY=1 —\n"
            "               a test harness, never production)\n\n"
            "--plant N turns the run into a full gate check: plant N throws, "
            "attack over --windows TTL windows, then print PASS/FAIL for whether "
            "any planted throw was stolen and whether an honest read survived.\n\n"
            "The live-deployment gate run is a MANUAL, human-in-the-loop founder step."
        ),
    )
    parser.add_argument("--target", default="http://127.0.0.1:8000",
                        help="base URL of the running instance (default: %(default)s)")
    parser.add_argument("--mode", choices=("single-ip", "botnet"), default="single-ip",
                        help="attack shape (default: %(default)s)")
    parser.add_argument("--ips", type=int, default=100,
                        help="botnet mode: number of distinct source IPs to imitate "
                             "(default: %(default)s)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="seconds to attack per window (default: %(default)s; "
                             "0 = until --attempts)")
    parser.add_argument("--attempts", type=int, default=0,
                        help="stop after this many attempts (0 = unlimited, "
                             "bounded by --duration)")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="number of concurrent requests in flight "
                             "(default: %(default)s)")
    parser.add_argument("--plant", type=int, default=0, metavar="N",
                        help="gate-check mode: plant N throws, attack, verify none "
                             "were stolen and an honest read still works")
    parser.add_argument("--windows", type=int, default=3,
                        help="gate-check mode: how many TTL windows to attack over "
                             "(default: %(default)s)")
    parser.add_argument("--slow-threshold", type=float, default=0.5, dest="slow_threshold",
                        help="a miss taking at least this many seconds is counted as "
                             "tarpitted (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="per-request timeout in seconds (default: %(default)s)")
    parser.add_argument("--header", default="X-Forwarded-For",
                        help="forwarding header used in botnet mode "
                             "(default: %(default)s; app also honours CF-Connecting-IP)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = args.target.rstrip("/")

    if args.plant > 0:
        return asyncio.run(run_gate_check(args))

    print(f"[attack] {args.mode} against {base} for "
          f"{args.duration}s @ concurrency {args.concurrency} ...")
    stats = asyncio.run(
        run_attack(
            base,
            mode=args.mode,
            ips=args.ips,
            duration=args.duration,
            max_attempts=args.attempts,
            concurrency=args.concurrency,
            slow_threshold=args.slow_threshold,
            timeout=args.timeout,
            header_name=args.header,
        )
    )
    print_report(stats, base, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
