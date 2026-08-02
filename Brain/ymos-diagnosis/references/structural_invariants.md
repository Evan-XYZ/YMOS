# Structural invariants

These criteria apply across strategy families. They evaluate whether a strategy is operable and auditable, not whether it is profitable.

## 1. Expressibility

A strategy should identify:

- Scope: markets, instruments, and situations it addresses.
- Entry: what evidence makes an opportunity eligible.
- Invalidation: what observable evidence says the thesis is wrong.
- Risk bearing: how exposure and tolerable loss are bounded.
- Horizon: how long the thesis needs and how long funds are available.
- Exit: what happens when evidence, time, or portfolio constraints change.

The strategy does not need to be fully mechanical, but hidden discretionary judgments must be named.

## 2. Internal consistency

Entry, invalidation, sizing, and horizon need compatible judges or an explicit priority rule.

Examples of conflicts:

- Enter on a long-horizon fundamental thesis, then invalidate on ordinary short-horizon noise without defining why price has authority.
- Enter for a time-bounded event, then remove the deadline after the event fails.
- Claim a low-frequency strategy while consuming intraday signals that repeatedly override it.
- Size as if an outcome is diversified when positions share the same underlying exposure.

## 3. Falsifiability

Important claims need observable disconfirming evidence. “The company is still good”, “the market will understand later”, and “I will know when to leave” are not falsifiable rules.

A usable invalidation statement has:

```text
claim → observable counter-signal → evidence source → action → review window
```

## 4. Risk-bearing clarity

The user—not the diagnostician—chooses numbers. The structure must still reveal:

- What base is used for sizing.
- What loss-bearing unit is being budgeted.
- Whether multiple positions share one risk factor.
- Whether fund availability can carry the thesis horizon.
- Whether exit remains under the user's control.

## 5. Decision/execution separation

The user should know which judgments must be completed outside the execution window and which actions may be performed during it. A plan that permits unrestricted rule invention during execution is not a plan.

## 6. Truth-source integrity

Original thesis, prepared action, actual execution, later adjustment, and result validation must be distinguishable. Historical evidence must be append-only or otherwise protected from silent hindsight edits.

## 7. Feedback governance

Repeated gaps may justify a rule-change proposal. A proposal is not a validated rule until it includes:

- Trigger evidence.
- Before and after.
- Expected effect.
- Falsification condition.
- Review sample or date.
- Human approval.
- Rollback path.

## Four cause types

Always separate:

1. Strategy operated as designed; outcome was unfavorable.
2. Execution deviated from an existing rule.
3. Strategy rules were vague, missing, or contradictory.
4. Research or driver evidence was missing, stale, or wrong.

Only the third normally calls for a strategy-rule rewrite.
