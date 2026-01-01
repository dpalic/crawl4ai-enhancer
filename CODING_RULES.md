# Coding Rules

## Functions and returns
- Use a single exit point per function; avoid multiple early returns.
- Keep returns simple: `return some_named_variable`. Do not return complex expressions directly; assign to a variable first.
- Assign intermediate results to named variables before returning to keep intent clear.

## Branching
- Every branch (`if` / `elif` / `else` or `try` / `except`) must include a short comment explaining why that path exists. Place the comment on its own line inside the branch before the logic, not trailing the condition.
- Keep branching shallow; refactor nested logic into helper functions when necessary.
- Wrap conditional expressions in parentheses to make grouping explicit and prevent later precedence mistakes.

## Documentation
- Add docstrings to all functions and methods, documenting parameters and return values.
- Document classes with a class-level docstring summarizing purpose and key behaviors.
- Document class fields (attributes) with inline comments or in the class docstring.
- Document constants and enum values with inline comments stating meaning and usage.
- Follow PEP 257 docstring conventions for consistent documentation style.

## Constants and enums
- Prefix shared constants clearly and place a brief inline comment describing intent and units.
- For enums, document each value with a short comment that clarifies when to use it.

## Output / logging
- Avoid complex expressions inside `print`/logging statements. Compute values in named variables first, then interpolate those simple variables in the message.

## Formatting (PEP 8 alignment)
- Follow PEP 8: 4 spaces per indent; do not use tabs. Never mix tabs and spaces.

## Validation routines
- When validating user input or documents, do not return on the first failure; collect and report all detectable validation issues so the caller sees the full set in one pass.

## Validation design
- Define core validators in `escavia_travel_agency_manager/domain/...` as framework-agnostic helpers that return `ValidationOutcome` with `ValidationIssue` entries. Avoid side effects and `frappe.throw` inside core validators. Code under `domain` should stay ERPNext/Frappe agnostic for reuse in other contexts.
- Represent validator inputs with dataclasses (e.g., promotions, pricing) to make required/optional fields explicit; avoid raw dicts.
- Accumulate all issues (no early returns); classify with `ValidationStatus` (ERROR/WARNING/SUCCESS).
- Keep validators single-purpose and compose them in orchestration layers (hooks, services) rather than duplicating logic.
- Surface user-facing formatting (e.g., HTML bullet lists) only in the consuming layer; core validators should emit plain descriptions.
- Add unit tests for each validator plus at least one integration-style test that exercises the validator in its ERPNext usage (e.g., via the hook or service that consumes it). Include these tests in `run_tests.sh`/pytest suites.

## File moves and renames
- Use `git mv` for file or folder moves/renames to preserve history and simplify reviews.
