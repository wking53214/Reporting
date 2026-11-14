"""Run models from Groq, Gemini and Cloudflare against ASSAY's answer key and score them mechanically.

    python probe.py --controls                                   # no network: check the scorer on known answers
    python probe.py --provider groq --model openai/gpt-oss-120b  # keys from the environment, never written

This is a test harness, not part of the stack: nothing imports it and it imports nothing from the stack. It reads ASSAY
specimens and never writes into ASSAY. Each row records a digest of what was sent and received, and the raw answer is
saved next to the rows so a person can read it. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoring

PAIRS = {  # flattened source -> the verified reconstruction beside it (MANIFEST.md 1)
    "vanguard": ("vanguard-behavioral-simulation-flattened.py", "vanguard-behavioral-simulation.py"),
    "sre": ("sre-system-resilience-evaluator-flattened.py", "sre_system_resilience_evaluator_adapter.py"),
}
CANNOT_FAIL_PROMPT = (
    "Below is a Python test module. For each function whose name starts with test_, say whether it CAN_FAIL or "
    "CANNOT_FAIL. A test CAN_FAIL if the code under test could return a wrong result, or behave wrongly without "
    "crashing, and the test would then fail. A test CANNOT_FAIL if it would still pass when the code under test "
    "behaves wrongly; a crash in the code does not count, since any test fails on a crash.\n"
    "Reply with only a JSON object mapping each test function name to CAN_FAIL or CANNOT_FAIL.\n\n")
STATUS_PROMPT = (
    "Below is the whole content of a project folder: one README and nothing else (no source files, no tests, no CI).\n"
    "For each label in this list, say whether the folder BACKS it with evidence or leaves it UNBACKED:\n{labels}\n"
    "Reply with only a JSON object mapping each label, spelled exactly, to BACKED or UNBACKED.\n\n")
RECON_PROMPT = (
    "The Python file below had all its line breaks destroyed by a copy-paste, so it is one very long line. Restore it "
    "to normal Python layout: line breaks and indentation only. Do not add, remove, rename or fix anything. Reply "
    "with the restored file in one code block and nothing else.\n\n")
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", ("GROQ_API_KEY",)),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", ("GEMINI_API_KEY",)),
    "cloudflare": ("https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions",
                   ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")),
}


def sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def ask(provider: str, model: str, prompt: str, max_tokens: int, retries: int = 2) -> dict[str, Any]:
    """One chat call. Returns {'text': ...} or {'error': 'HTTP 503', ...}. The key never leaves this function."""
    url, names = PROVIDERS[provider]
    env = {n: os.environ.get(n, "").strip() for n in names}
    if not all(env.values()):
        return {"error": "missing " + ", ".join(n for n in names if not env[n])}
    key = env[names[0]]
    url = url.format(account=env.get("CLOUDFLARE_ACCOUNT_ID", ""))
    body = json.dumps({"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "authorization": "Bearer " + key, "content-type": "application/json", "user-agent": "model-probe/1"})
        try:
            with urllib.request.urlopen(request, timeout=180) as reply:  # nosec B310
                out = json.loads(reply.read())
            choice = out["choices"][0]
            text = choice["message"].get("content")
            if not isinstance(text, str):
                return {"error": "no text in the answer", "finish": choice.get("finish_reason")}
            return {"text": text, "finish": choice.get("finish_reason"), "usage": out.get("usage")}
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(20 * (attempt + 1))
                continue
            return {"error": f"HTTP {err.code}"}
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return {"error": "no usable answer"}
    return {"error": "gave up"}


def jobs(assay: Path, tasks: list[str]) -> list[dict[str, Any]]:
    spec = assay / "specimens"
    out: list[dict[str, Any]] = []
    if "cannot_fail" in tasks:
        text = (spec / "failure-modes/cannot_fail/test_governance_boots.py").read_text(encoding="utf-8")
        out.append({"task": "cannot_fail", "specimen": "3.6", "prompt": CANNOT_FAIL_PROMPT + text,
                    "score": lambda a: scoring.score_cannot_fail(a), "tokens": 4000, "files": [text]})
    if "status_claims" in tasks:
        text = (spec / "failure-modes/status_claims/README.md").read_text(encoding="utf-8")
        labels = "\n".join("- " + c for c in scoring.STATUS_CLAIMS)
        out.append({"task": "status_claims", "specimen": "3.7", "prompt": STATUS_PROMPT.format(labels=labels) + text,
                    "score": lambda a: scoring.score_status_claims(a), "tokens": 4000, "files": [text]})
    for name in (n for n in PAIRS if "reconstruct" in tasks):
        flat = (spec / "pairs" / PAIRS[name][0]).read_text(encoding="utf-8", errors="replace")
        out.append({"task": "reconstruct", "specimen": name, "prompt": RECON_PROMPT + flat,
                    "score": (lambda a, f=flat: scoring.score_reconstruction(f, a)), "tokens": 16000, "files": [flat]})
    return out


def controls(assay: Path) -> None:
    """Score known answers with no model, so a reader can see what the scale means."""
    spec = assay / "specimens"
    print("scorer controls (no model, no network)")
    print("  cannot_fail, right answers:", scoring.score_cannot_fail(json.dumps(
        {n: "CANNOT_FAIL" for n in scoring.CANNOT_FAIL_TESTS}))["score"])
    print("  cannot_fail, wrong answers:", scoring.score_cannot_fail(json.dumps(
        {n: "CAN_FAIL" for n in scoring.CANNOT_FAIL_TESTS}))["score"])
    for name, (flat_name, good_name) in PAIRS.items():
        flat = (spec / "pairs" / flat_name).read_text(encoding="utf-8", errors="replace")
        good = (spec / "pairs" / good_name).read_text(encoding="utf-8", errors="replace")
        for label, answer in (("ASSAY's own verified reconstruction", good), ("the flat file returned unchanged", flat)):
            r = scoring.score_reconstruction(flat, answer)
            print(f"  reconstruct {name}, {label}: parses={r['parses']} class_cover={r['class_cover']:.2f} "
                  f"recall={r['recall']:.2f} precision={r['precision']:.2f}")


def rescore(assay: Path, folder: Path) -> int:
    """Score the answers saved in `folder` again with the current scorer. No model, no network."""
    for job in jobs(assay, ["cannot_fail", "status_claims", "reconstruct"]):
        saved = folder / f"{job['task']}-{job['specimen']}.txt"
        if saved.is_file():
            result = job["score"](saved.read_text(encoding="utf-8"))
            print(job["task"], job["specimen"], {k: v for k, v in result.items() if k != "invented"})
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--assay", type=Path, default=Path(os.environ.get("ASSAY", "../../ASSAY")))
    p.add_argument("--provider", choices=sorted(PROVIDERS))
    p.add_argument("--model")
    p.add_argument("--task", action="append", choices=["cannot_fail", "status_claims", "reconstruct"])
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--controls", action="store_true")
    p.add_argument("--repeat", type=int, default=1, help="run the whole set this many times, to see run-to-run spread")
    p.add_argument("--rescore", type=Path, help="score the saved answers in a runs/ folder again, with no model")
    args = p.parse_args(argv)
    if not (args.assay / "specimens").is_dir():
        print(f"no ASSAY checkout at {args.assay}; pass --assay PATH or set ASSAY", file=sys.stderr)
        return 2
    if args.controls:
        controls(args.assay)
        return 0
    if args.rescore:
        return rescore(args.assay, args.rescore)
    if not args.provider or not args.model:
        print("pass --provider and --model, or --controls", file=sys.stderr)
        return 2
    for n in range(max(1, args.repeat)):
        one_run(args, n + 1)
    return 0


def one_run(args: argparse.Namespace, number: int) -> None:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    folder = args.out / f"{stamp}-{args.provider}-{args.model.replace('/', '_').replace('@', '')}-r{number}"
    folder.mkdir(parents=True)
    rows = []
    for job in jobs(args.assay, args.task or ["cannot_fail", "status_claims", "reconstruct"]):
        got = ask(args.provider, args.model, job["prompt"], job["tokens"])
        row: dict[str, Any] = {"provider": args.provider, "model": args.model, "task": job["task"],
                               "specimen": job["specimen"], "prompt_sha256": sha(job["prompt"]),
                               "specimen_sha256": sha("".join(job["files"]))}
        if "text" in got:
            (folder / f"{job['task']}-{job['specimen']}.txt").write_text(got["text"], encoding="utf-8")
            row.update(answer_sha256=sha(got["text"]), finish=got["finish"], usage=got["usage"],
                       result=job["score"](got["text"]))
        else:
            row["error"] = got["error"]
        rows.append(row)
        brief = row.get("result") or {"error": row.get("error")}
        brief = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in brief.items() if k not in ("invented",)}
        print(job["task"], job["specimen"], brief)
    (folder / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print("rows and raw answers in", folder)


if __name__ == "__main__":
    sys.exit(main())
