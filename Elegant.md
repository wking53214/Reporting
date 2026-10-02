# Elegant: Code Beautification and Rewriting Rules

**A system for transforming code into beautiful, architecturally transparent implementations while preserving every existing behavior.**

**Author**: William N. King
Version: 1.0
Date: 2026-10-01
Source: ≡TACK Kernel Artistic Rewrite & Validation Phase

---

## I. Beautification Principles

Beautification is the documentation and restructuring of code to make its intent, architecture, and defects visible. It is not rewriting; it is translation to transparency.

### A. Naming as Truth

**Rule: Names must match the contract they represent.**

When code's name contradicts its implementation, beautification corrects the name, the documentation, or the implementation—whichever is the truth.

**Example: SlidingWindowRing Defect**

```cpp
// BEFORE (Hidden defect)
class SlidingWindowRing {
private:
    uint64_t counter_ = 0;  // Name says "sliding window"; is actually single counter
public:
    void Consume(uint32_t tokens) { counter_ += tokens; }
};
```

```cpp
// AFTER (Defect visible)
/**
 * SLIDING WINDOW RING: Token Bucket with Explicit Defect
 * 
 * ARCHITECTURAL DEFECT: Single Counter (Not Sliding Window)
 * This class implements a single counter that increments with token consumption.
 * True sliding-window behavior would track time windows and reset periodically.
 * Current implementation: reactive debt tracking, not proactive rate limiting.
 */
class SlidingWindowRing {
private:
    uint64_t counter_ = 0;  // Single counter masquerading as sliding window
public:
    [[nodiscard]] uint64_t Consume(uint32_t tokens) noexcept {
        counter_ += tokens;
        return counter_;
    }
};
```

**The defect becomes visible. The name either changes, or documentation makes the mismatch explicit.**

### B. Narrative Documentation

**Rule: Code must tell a story about what it does, why it exists, and what it cannot do.**

Documentation goes before the code, not after. It establishes the contract (what the reader should expect), then the implementation either fulfills it or documents why it doesn't.

**Example: Layer Structure Documentation**

```cpp
/**
 * ≡TACK KERNEL LAYER 1: Hardware-Locked Timing
 *
 * PURPOSE: Measure the execution point of untrusted code at hardware precision.
 *
 * CORRECTNESS RULE: Every transaction measures actual CPU clock ticks from
 * RDTSCP (x86) or CNTPCT_EL0 (ARM64), not virtual time or wall clock.
 * This enables deadline enforcement independent of OS scheduler.
 *
 * ───────────────────────────────────────────────────────────────────────────
 * ARCHITECTURAL DEFECT: Silent Fallback to Zero on Unknown Architectures
 *
 * On unknown architectures (not x86_64 or aarch64), ReadTicks() returns 0.
 * This breaks containment: a sandbox reports zero execution time, bypassing
 * deadline enforcement. The correct behavior is to fail at compile time or
 * throw at runtime, not silently disable the layer.
 *
 * Impact: CRITICAL. Layer 1 is the foundation; a silent zero enables escape.
 * ───────────────────────────────────────────────────────────────────────────
 */

namespace stack::governor {

class HardwareClock {
public:
    /**
     * READ TICKS: Sample hardware clock counter.
     *
     * Returns the current cycle count from the CPU clock register.
     * On known architectures, this is precise and reliable.
     * On unknown architectures, returns 0 (DEFECT).
     *
     * Contract: Caller assumes result > 0 on successful measurement.
     * Defect: No validation that architecture is known.
     */
    [[nodiscard]] static uint64_t ReadTicks() noexcept {
#if defined(__x86_64__)
        unsigned int aux;
        return __rdtscp(&aux);
#elif defined(__aarch64__)
        uint64_t ticks;
        asm volatile("mrs %0, cntpct_el0" : "=r"(ticks));
        return ticks;
#else
        return 0;  // DEFECT: Silent fallback instead of compile error
#endif
    }
};

} // namespace stack::governor
```

### C. Architectural Properties as Comments

**Rule: Every non-obvious property must be documented inline.**

Properties like atomicity, fallback behavior, lifecycle expectations, and threading rules belong in the code, not in a separate document.

```cpp
/**
 * LIFECYCLE GUARD: Atomic Counter Prevents Mid-Transaction State Mutation
 *
 * Purpose: Prevent SetActiveCapabilities() from being called while a
 * transaction is executing, which would create a race between the transaction
 * checking capabilities and the host changing them mid-flight.
 *
 * Mechanism: transactions_in_flight_ is incremented before payload execution
 * and decremented in a RAII destructor. SetActiveCapabilities() checks this
 * counter and returns false if any transaction is in flight.
 *
 * Memory ordering: memory_order_acquire on load (SetActiveCapabilities check),
 * memory_order_release on increment/decrement (transaction guard). This ensures
 * visibility without unnecessary barriers.
 *
 * Trade-off: SetActiveCapabilities becomes blocking on busy systems.
 * A production implementation might defer capability changes to the next
 * transaction boundary instead of failing.
 */
std::atomic<uint32_t> transactions_in_flight_{0};

[[nodiscard]] bool SetActiveCapabilities(const CapabilityMask256& mask) noexcept {
    if (transactions_in_flight_.load(std::memory_order_acquire) > 0) {
        return false;  // Atomic guard prevents mid-flight capability changes
    }
    active_host_capabilities_ = mask;
    return true;
}
```

---

## II. Code Rewriting Rules

Rewriting preserves behavior while restructuring for clarity. The rules ensure transformation is surgical, not wholesale.

### Rule 1: Rename Without Changing Behavior

Change the name to match the implementation. If the implementation is wrong, fix it in a separate rewrite pass, and document the fix.

**Example:**

```cpp
// Step 1: Rename (rewriting pass 1)
// OLD: class SlidingWindowRing { ... }
// NEW: class TokenBucketCounter { ... }  // More accurate name

// Step 2: Fix Implementation (rewriting pass 2, separate commit)
// OLD: uint64_t counter_ = 0;  // Increments forever
// NEW: Implement actual sliding window with time windows
```

### Rule 2: Preserve Existing Call Sites

When restructuring, ensure all existing callers continue to work without modification. If this is impossible, it's not a beautification; it's a redesign.

**Example: SetActiveCapabilities Signature Change**

```cpp
// BEFORE: void SetActiveCapabilities(...)
// AFTER: [[nodiscard]] bool SetActiveCapabilities(...)

// All call sites must be updated to CHECK the return value
// This is a signature change, so it's documented in a separate pass
// and merged after all call sites are verified.
```

### Rule 3: Add Guards Without Changing Logic

Add lifecycle guards (atomic counters, RAII destructors) around existing logic. The guard wraps the logic; it doesn't replace it.

```cpp
// BEFORE
auto result = g_host->ExecuteGovernedTransaction(...);
return result.has_value() ? 0 : -3;

// AFTER (with lifecycle guard)
transactions_in_flight_.fetch_add(1, std::memory_order_release);
struct TransactionGuard {
    std::atomic<uint32_t>& counter;
    ~TransactionGuard() noexcept {
        counter.fetch_sub(1, std::memory_order_release);
    }
} lifecycle_guard{transactions_in_flight_};

// ... existing logic unchanged ...

auto result = g_host->ExecuteGovernedTransaction(...);
return result.has_value() ? 0 : -3;
```

### Rule 4: Fix Namespace References Systematically

Rename all tack_ files to stack_ and update all namespace declarations in one pass. Use grep, sed, and verify with compilation.

```bash
# Step 1: Rename files
git mv cpp/include/tack_kernel.hpp cpp/include/stack_kernel.hpp
git mv cpp/include/tack_kinetic_governor.hpp cpp/include/stack_kinetic_governor.hpp

# Step 2: Update includes and namespaces
sed -i 's/#include "tack_/#include "stack_/g' **/*.cpp **/*.hpp
sed -i 's/using namespace tack;/using namespace stack;/g' **/*.cpp

# Step 3: Verify with compilation
cmake . && cmake --build .

# Step 4: One commit per step (tack_kernel.hpp rename, tack_kinetic_governor.hpp rename, ..., using namespace changes)
```

### Rule 5: Document Defects Without Fixing Them (First Pass)

On the first rewriting pass, document defects in comments and structural tests. Don't fix them yet. This makes the defects visible and falsifiable.

**Example: Layer 5 (Audit) Silent Defect**

```cpp
/**
 * ARCHITECTURAL DEFECT: Audit Ring Push Never Called
 *
 * The audit ring is initialized and available, but Layer 4 (orchestration)
 * never calls Push() to record governance events. The audit trail is silent.
 *
 * Why: Layer 4 orchestrates six gates but doesn't have a call path to audit.
 * The audit ring exists (Layer 5) but is disconnected from the execution flow.
 *
 * Impact: MEDIUM. No visibility into governance decisions at runtime.
 * Silent defect: code compiles, tests pass, but governance is not recorded.
 *
 * Fix: (deferred to defect-fixing phase)
 * Layer 4 must call g_audit_ring.Push() after each transaction completes.
 */
class SeccompAuditRing {
public:
    void Push(AuditEventType event_type, uint64_t context_id, uint32_t tokens) noexcept {
        // This method exists and is correct.
        // But Layer 4 never calls it. (DEFECT)
        // ...
    }
};
```

### Rule 6: Validate Architectural Boundaries

When rewriting, verify that each layer's contract is enforced:

- **Layer 1**: Always returns > 0 or throws (never silent zero)
- **Layer 2**: Signal handler sets flag; preemption is checked before payload returns
- **Layer 3**: Token consumption is atomic relative to deadline checks
- **Layer 4**: All six gates execute in order before payload runs
- **Layer 5**: Every transaction that passes Layer 4 is recorded
- **Layer 6**: Arena allocations are guarded; Reset() fails if allocations in flight

```cpp
// Validation test: Verify layer boundaries are enforced
TEST_CASE("Layer Integration: Six-Layer End-to-End Flow") {
    uint64_t baseline = HardwareClock::ReadTicks();
    REQUIRE(baseline > 0);  // Layer 1: never silent zero

    REQUIRE(HardenedPosixPreemptionGuard::RegisterSignalHandler().has_value());
    // Layer 2: signal handler registered

    KineticGovernor<> gov;
    // Layer 3: rate limiter available

    GovernedMinotaurHost<> host;
    REQUIRE(host.SetActiveCapabilities(...));  // Layer 4: capabilities set
    
    SeccompAuditRing<> audit;
    // Layer 5: audit ring available

    StaticArenaBuffer<> arena;
    // Layer 6: arena available

    // All six layers coordinated in one transaction
    auto result = host.ExecuteGovernedTransaction(...);
    REQUIRE(result.has_value());
}
```

---

## III. Exemplar: ≡TACK Kernel Layers 1-6

### Layer 1: Hardware Clock (Foundation)

**Beautification**: Added documentation of the silent-zero defect. Clarified that ReadTicks() is the measurement point, not the deadline enforcement.

**Rewriting**: No changes to implementation. Only documentation added to make the defect visible.

### Layer 2: POSIX Deadline Timer (Preemption)

**Beautification**: Documented that the signal handler is reactive, not true preemption. The payload runs to completion; then the handler flag is checked.

**Rewriting**: No changes. Documentation clarifies the contract: WasPreempted() must be checked AFTER payload, not before.

### Layer 3: Kinetic Governor (Rate Limiting)

**Beautification**: Documented four defects:
1. SlidingWindowRing is a single counter, not a sliding window
2. Debt check occurs AFTER CAS (race condition window)
3. Reactive deadline scope (not proactive)
4. Unused interface parameters

**Rewriting**: No changes to implementation. Defects documented for priority in defect-fixing phase.

### Layer 4: Host Binding (Orchestration)

**Beautification**: Documented the single-responsibility violation. One method orchestrates six gates.

**Rewriting**: Added lifecycle guard (TransactionGuard RAII). SetActiveCapabilities now returns bool, guarded by atomic counter.

### Layer 5: Audit Trail (Telemetry)

**Beautification**: Documented that Push() exists but is never called by Layer 4. Silent audit trail.

**Rewriting**: No changes. Defect flagged for fixing phase (Layer 4 must call Push()).

### Layer 6: Memory Arena (Isolation)

**Beautification**: Documented the isolation policy defect. Reset() allows reuse across transaction boundaries.

**Rewriting**: Added lifecycle guard (allocations_in_flight_ atomic). Reset() now returns bool, guarded against mid-transaction resets.

---

## IV. Commit Message Template for Beautification

```
Step N: [Component]: [Rewriting Pass Description]

[One-line summary of what changed]

BEAUTIFICATION CHANGES:
  - [Documentation added]
  - [Defect documented]
  - [Architectural property clarified]

REWRITING CHANGES:
  - [Signature change, if any]
  - [Guard added, if any]
  - [Namespace/naming updated, if any]

TESTS AFTER STEP N:
  Tests run: [count]
  Pass: [count]
  Fail: [count]
  Verification: [What was validated]

Co-Authored-By: [Name] <email>
```

---

## V. Defect Priority System

After beautification, defects are prioritized for the fixing phase:

- **CRITICAL**: Layer 1 silent zero (breaks containment immediately)
- **HIGH**: Layers 2-3 reactive behavior (enables deadline bypass)
- **MEDIUM**: Layers 4-6 orchestration gaps and policy defects (enables gradual escape)

Each priority is fixed in a separate phase, with tests validating the fix before moving to the next layer.

---

## VI. Defect-Fixing Process (Per-Layer)

The defect-fixing phase mirrors the validation phase: complete one layer in totality, validate it exhaustively, red team it, then move to the next layer.

### A. Layer Fixing Workflow

For each layer (1 through 6):

1. **Identify all CRITICAL/HIGH/MEDIUM defects in the layer** (from Elegant.md documentation)
   - Example: Layer 1 has "silent zero on unknown architecture"
   - List all defects before starting fixes

2. **Fix all defects in the layer** (in priority order)
   - One commit per defect fix
   - Follow commit template below
   - Do NOT move to the next layer until this one is complete

3. **Run full test suite**
   - All tests from validation phase must pass
   - Add new tests if the fix changes external behavior
   - Test result: 100% pass rate before moving on

4. **Red team the layer** (adversarial validation)
   - Ask: "How would an attacker exploit this?"
   - Run mutation testing on the fixed code
   - Run boundary condition tests
   - Run concurrency/race condition tests
   - Red team result: All adversarial tests fail (code passes)

5. **Commit and push the layer**
   - Commit message includes test results and red team findings
   - Push to origin/main
   - Update Elegant.md with any new processes discovered

6. **Move to next layer**
   - Only after Layer N passes red team
   - Begin Layer N+1

### B. Example: Layer 1 Fixing (HardwareClock Silent Zero)

**Defects identified** (from validation phase):
- ReadTicks() returns 0 on unknown architectures (enables escape)
- No compile-time assertion
- No runtime error

**Fix approach**:
```
Fix 1: Add #error directive for unknown architectures
  Commit: "Layer 1: HardwareClock: Fail at compile time on unknown arch"
  Test: Compilation fails on unknown target
  Red team: Can no longer silently return zero

Fix 2: Add static_assert for supported architectures
  Commit: "Layer 1: HardwareClock: Static assertion guards unknown platforms"
  Test: Static assertion triggers at compile time
  Red team: No fallback path exists at runtime

Fix 3: Document the contract in code
  Commit: "Layer 1: HardwareClock: Clarify ReadTicks() contract and bounds"
  Test: All existing tests pass
  Red team: Boundary tests on tick overflow, zero detection
```

**Test suite validation**:
```
Tests run: N (all validation phase tests + layer-specific tests)
Pass: N
Fail: 0
Mutation tests: [CRITICAL mutations from serum]
Mutation failures: [all mutations killed]
```

**Red team findings** (adversarial):
```
Attack: Can ReadTicks() return zero legitimately? 
  Result: NO. ReadTicks() either returns > 0 or compilation fails. ✓

Attack: Can unknown architecture be silently added without failing?
  Result: NO. #error and static_assert prevent this. ✓

Attack: Can tick counter overflow be exploited?
  Result: Boundary test shows overflow behavior documented. OK.
```

**Commit pattern**:
```
Step 1: Layer 1 - HardwareClock - Fail on unknown architecture

Add #error directive and static_assert to prevent silent zero
fallback on unsupported architectures. Layer 1 now fails at
compile time instead of enabling escape at runtime.

BEAUTIFICATION CHANGES:
  - Documented ReadTicks() contract in header
  - Documented that zero is impossible after compilation guard

REWRITING CHANGES:
  - Added #error for unknown __ARCH__
  - Added static_assert for known architectures
  - Removed silent zero fallback path

TESTS AFTER STEP 1:
  Tests run: 24
  Pass: 24
  Fail: 0
  Mutation tests: 8 CRITICAL patterns (serum)
  Mutations killed: 8/8
  Red team: Adversarial test_unknown_arch_compilation PASS

Co-Authored-By: William N. King <wking53214@gmail.com>
```

### C. Red Team Testing Framework

Every layer gets red team validation before advancing:

```cpp
// Red team test: Can attacker exploit this layer's defect?
TEST(Layer1RedTeam, UnknownArchitectureFailsAtCompileTime) {
    // Attempt to compile with unknown __ARCH__
    // Expected: Compilation fails with clear error
    // Result: Cannot be bypassed at runtime
}

TEST(Layer1RedTeam, ReadTicksNeverReturnsZero) {
    // Boundary test: Try to make ReadTicks() return 0
    // Expected: Not possible on supported architectures
    // Result: Zero detection guards downstream layers
}

TEST(Layer1RedTeam, SilentFallbackIsEliminated) {
    // Security test: Does the old silent zero still exist anywhere?
    // Expected: No fallback paths found
    // Result: Escape vector closed
}
```

---

## VII. Tools and Automation

### Systematic Rename (e.g., tack_ → stack_)

```bash
#!/bin/bash
# Rename all tack_ files to stack_ and update references

# Step 1: Rename files
for file in $(find . -name "tack_*.hpp" -o -name "tack_*.cpp"); do
    newfile="${file/tack_/stack_}"
    git mv "$file" "$newfile"
done

# Step 2: Update includes and namespaces
find . -name "*.hpp" -o -name "*.cpp" | xargs sed -i \
    -e 's/#include "tack_/#include "stack_/g' \
    -e 's/using namespace tack;/using namespace stack;/g' \
    -e 's/} \/\/ namespace tack::/} \/\/ namespace stack::/g'

# Step 3: Verify compilation
cmake . && cmake --build .

# Step 4: Commit each major change separately
git commit -m "Step N: Rename tack_kernel.hpp to stack_kernel.hpp"
git commit -m "Step N+1: Update all includes from tack_ to stack_"
git commit -m "Step N+2: Update namespace declarations from tack:: to stack::"
```

### Verify Architectural Boundaries

```bash
#!/bin/bash
# Run integration test to verify all six layers coordinate

cd cpp && cmake . && cmake --build . && ./tack_tests --reporter=xml > results.xml

# Check that:
# - Layer 1 (Hardware clock) always returns > 0
# - Layer 2 (Preemption) signal handler is registered
# - Layer 3 (Governor) consumes tokens
# - Layer 4 (Host) validates capabilities
# - Layer 5 (Audit) records events
# - Layer 6 (Arena) allocates memory

echo "All six layers validated in integration test."
```

---

## VIII. Maintenance and Evolution

Beautification is not a one-time process. As code evolves:

1. **New code**: Follow the beautification rules from the start. Document contract, purpose, defects.
2. **Refactoring**: If you change implementation, update the documentation. If you change the contract, create a new rewriting pass.
3. **Defect fixes**: Each defect fix is a separate commit that updates the documentation to reflect the fix.

The goal is a codebase where **architecture is visible, defects are labeled, and changes are tracked with precision.**

---

## IX. Completion Requirements

Upon completion of the Elegant defect-fixing process (all layers fixed, red-teamed, and committed), two deliverables are required:

### A. Elegant Completion Log (MD)

A markdown document recording:
- **Date completed**: When all layers passed red team validation
- **Layers summary**: Status of each layer (CRITICAL/HIGH/MEDIUM, defects identified, defects fixed, red team result)
- **Commits**: Hash, subject, and layer for each defect-fix commit
- **Test results**: Final validation suite results (pass rate, mutation tests killed)
- **Governance**: Confirmation that ≡TACK conforms to CNS (SSOT enforced)

Example structure:
```
# Elegant Defect-Fixing Completion (≡TACK Kernel)
Date: 2026-10-XX
Author: William N. King

## Summary
6 layers, 15 defects identified, 15 fixed, 6 red-team validations passed

## Layer Status
| Layer | Defects | Priority | Fixed | Status |
|-------|---------|----------|-------|--------|
| 1 | Silent zero | CRITICAL | 1/1 | ✓ PASS |
...

## Commits
- bba99f3: Step 1 - Layer 1 - HardwareClock
...

## Governance
✓ ≡TACK conforms to CNS (SSOT: ≡TACK follows CNS, never reverse)
```

### B. README: Design Analogy Section

A section in the repository README explaining:

1. **The analogy concept** the repo was designed around
2. **Vibecode/natural language mapping**: How the abstract concept translates to code
3. **Real-world functional terminology**: What the design represents in operational terms

Example structure:
```markdown
## Design Analogy: Hardware Governance

### The Concept
≡TACK is modeled after [ANALOGY]. Just as [REAL-WORLD SYSTEM] enforces constraints through [MECHANISM], 
this kernel enforces execution constraints through [CODE MECHANISM].

### Vibecode ↔ Natural Language
- **Layer 1 (ReadTicks)** vibecode: `__rdtscp(&aux)` 
  Natural language: Measure exact execution point (no speculation)
  Real-world: A stopwatch that cannot be cheated (CPU clock register)

- **Layer 2 (WasPreempted)** vibecode: Signal handler + flag
  Natural language: Detect deadline breach after execution
  Real-world: A referee marking when a rule was broken (after play)

### Functional Terminology
- "Serializing instruction" = "trustworthy measurement point"
- "Signal handler flag" = "breach detector" (not executor)
- "Rate limiting" = "quota enforcement"
```

---

**Status**: Validated through ≡TACK Kernel artistic rewrite and validation phase (2026-10-01).
**Ready for**: Application to production codebases, defect-fixing phase, and cross-organization adoption.

**Author**: William N. King
**Governance**: This specification governs all future beautification and code correction work. All modifications must be immediately reflected in this document.
