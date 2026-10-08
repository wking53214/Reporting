# Elegant: Code Beautification and Rewriting Rules

**A system for transforming code into beautiful, architecturally transparent implementations while preserving every existing behavior.**

**Author**: William N. King  
**Version**: 1.2  
**Date**: 2026-10-07  
**Source**: ≡TACK Kernel Artistic Rewrite & Validation Phase; refined after application to `wking53214/experimental`, `wking53214/ghost_tools` and `wking53214/Elegant`

---

## I. Beautification Principles

Beautification is the documentation and restructuring of code to make its intent, architecture, and defects visible. It is not rewriting; it is translation to transparency.

### A. Naming as Truth
**Rule: Names must match the contract they represent.**

### B. Narrative Documentation
**Rule: Code must tell a story about what it does, why it exists, and what it cannot do.**

### C. Architectural Properties as Comments
**Rule: Every non-obvious property must be documented inline.**

---

## II. Code Rewriting Rules

### Rule 1: Rename Without Changing Behavior
### Rule 2: Preserve Existing Call Sites
### Rule 3: Add Guards Without Changing Logic
### Rule 4: Fix Namespace / Naming References Systematically
### Rule 5: Document Defects Without Fixing Them (First Pass)
### Rule 6: Validate Architectural Boundaries

### Rule 7: Behavior-Preservation Gate (Hard)

**No beautification or fix commit merges without a green automated suite.**

| Gate | Requirement |
|------|-------------|
| Unit / integration suite | Pass count ≥ baseline; zero new failures |
| Invariant tests | Authority / safety invariants still pass |
| Multi-seed / property checks (if present) | Documented targets still met |
| Before/after | Record test counts in the commit message |

If the suite cannot protect invariants, **add tests before** changing behavior.

### Rule 8: Scope Control (Critical Path Default)

Default beautification scope is the **critical path**, not the entire repository.

1. Identify the invariant-bearing spine (e.g. authority → proposal → apply → detection).
2. Beautify and audit that spine first.
3. Expand outward only after a durable `ELEGANT_AUDIT.md` exists for the spine.

### Rule 9: Durable Defect IDs

Every defect gets a stable ID in a single source of truth (e.g. `ELEGANT_AUDIT.md`):

- Format: `C1`, `H1`, `M1`, `L1` (Critical / High / Medium / Low).
- IDs **never reuse** meanings once published.
- Every fix commit **must cite** the ID(s): `Fix H2: introduce OPERATOR_APPROVED`.
- Audit status: Open → Fixed (commit SHA).

### Rule 10: Re-Anchor Mutation Sites, Never Weaken Them

When a split or rename moves code that a mutation suite targets by exact text:

1. Re-point each moved site to its new text with the **same** mutation. Never delete a mutant to make a move pass.
2. A moved line must still match **exactly once**. If its new indentation makes it a substring of another site, make it unique (an inline comment is enough) rather than loosening the anchor.
3. Run every mutant suite that touches the changed file, not only the obvious one. Every mutant must still be killed.
4. Split along seams the code already has: a collection loop, one builder per kind of output, a verification step. Keep check order identical.

### Rule 11: Documentation Moves With Behavior

A commit that changes what a repository does changes what its README says, **in the same pull request**.

1. Before merge, run the repository's own self-check on itself (`elegant critic .`, `ghost-buster .`, `verify_manifest.py`) and record the result.
2. State counts in a form the self-check verifies ("24 tests exist"), not in prose it cannot read ("15 passed").
3. A live run that proves something gets a row in the repository's registry or audit file; the README points to it rather than asserting it.

---

## III. Defect Priority System

| Priority | Meaning |
|----------|---------|
| **CRITICAL** | Breaks containment / safety invariant immediately |
| **HIGH** | Enables bypass, audit lies, or race on the critical path |
| **MEDIUM** | Orchestration gaps, policy defects, gradual escape |
| **LOW** | Noise, env-sensitive thresholds, cosmetic mismatch |

---

## IV. Defect-Fixing Process

1. List open CRITICAL/HIGH/MEDIUM IDs from audit SSOT.
2. Fix one ID per commit.
3. Run full suite (Rule 7).
4. Red team: attacker goal blocked; prefer a regression test.
5. Update audit: Fixed + SHA.
6. Push; then next ID.

### Commit Template (Fixes)

```
Fix <ID>: <one-line summary>

ELEGANT:
  Defect: <ID> (<priority>)
  Layer/spine: <component>
  Red team: <attack> → <result>

TESTS:
  Run: <n>  Pass: <n>  Fail: 0
```

---

## V. Audit File (SSOT)

Each repo SHOULD keep `ELEGANT_AUDIT.md` with: design analogy, layer map, defect table (ID, priority, status, SHA), invariant properties, fix order.

---

## VI. Exemplars

### ≡TACK Kernel
Silent zero on Layer 1 = canonical CRITICAL defect.

### Self-Hardening Governance (`experimental`)
Spine: authority → proposal → governor apply → detection.
Defects at process adoption: H1 (swallowed exceptions), H2 (operator AUTO_APPROVED), M1/M3.

### Function splits (`ghost_tools`, 2026-10-07)
The self-scan rated two of ghost_tools' own functions MAJOR `long_function`.
`detect_unreachable_declared_state` 253 → 106 lines (member collection plus one builder per finding kind);
`_remedy_doc_counts` 184 → 137 lines (decisions made from the run alone; read-back verification).
Behavior unchanged, 12 mutation sites re-anchored (Rule 10), self-scan 0 MAJOR, CI green on 3.11 and 3.12.

### Documentation drift (`Elegant`, 2026-10-07)
Three behavior changes merged with no README change. `elegant critic .` on Elegant itself:
"This isn't good enough yet" (README said 15 tests; the tree had 24). Fixed by Rule 11:
README corrected, count restated so the critic checks it, the live loop run recorded in
`docs/REGISTRY.json`. Critic after: exit 0. The canonical case for Rule 11.

---

## VII. Version History

| Ver | Date | Change |
|-----|------|--------|
| 1.0 | 2026-10-01 | Initial principles, rules 1–6, ≡TACK exemplar |
| 1.1 | 2026-10-02 | Rules 7–9; audit SSOT; fix commit template; governance exemplar |
| 1.2 | 2026-10-07 | Rule 10 (re-anchor mutation sites), Rule 11 (documentation moves with behavior); ghost_tools split and Elegant drift exemplars |

**Author**: William N. King
