# Elegant: Code Beautification and Rewriting Rules

**A system for transforming code into beautiful, architecturally transparent implementations while preserving every existing behavior.**

**Author**: William N. King  
**Version**: 1.1  
**Date**: 2026-10-02  
**Source**: ≡TACK Kernel Artistic Rewrite & Validation Phase; refined after application to `wking53214/experimental`

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

---

## VII. Version History

| Ver | Date | Change |
|-----|------|--------|
| 1.0 | 2026-10-01 | Initial principles, rules 1–6, ≡TACK exemplar |
| 1.1 | 2026-10-02 | Rules 7–9; audit SSOT; fix commit template; governance exemplar |

**Author**: William N. King
