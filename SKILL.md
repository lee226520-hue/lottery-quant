---
name: lottery-quant
description: On every invocation, fetch current official lottery data, analyze historical records, and generate budget-bounded, rules-aware reports and number combinations for mainland China lottery games. Use when a user asks for live backfill, which game to buy, budget allocation, or automatic number selection; never purchase tickets, claim guaranteed profit, or present random-number patterns as predictive.
---

# Lottery Quant

Use this skill for a transparent lottery decision aid, not a prediction or betting service. The output should help a user spend no more than their stated entertainment budget, understand the odds and assumptions, and receive printable combinations when they explicitly ask for automatic selection.

## Hard boundaries

- Never promise a win, a positive expected value, an “inside” advantage, or improved draw probability. Every valid combination in the same game has the same draw probability.
- Never buy tickets, place bets, collect payment, run a wallet, arrange代购, or automate an online purchase. Only generate analysis and a ticket-like combination list. Mainland China currently prohibits unauthorized internet lottery sales; treat any purchase workflow as out of scope.
- Never recommend borrowing, chasing losses, increasing a budget after a loss, or using essential living money. If the user describes loss-chasing, debt, distress, or compulsive behavior, stop optimization and recommend pausing.
- Do not optimize for minors. Remind the user that lottery sales and redemption are restricted to adults under the applicable rules.
- For any report presented as current, attempt a fresh official sync first. Never silently treat an old local cache as today’s data. If official endpoints fail, say that current data could not be verified; use cached records only for a clearly labeled historical-only report or when the user explicitly requests offline analysis.
- Do not claim that a combination is globally unique across all users. A standalone open-source Skill has no knowledge of other installations. It can guarantee no duplicates within one generated portfolio, use a fresh cryptographic seed by default, and apply an anti-crowd heuristic; global uniqueness requires an optional shared reservation service.

## Input contract

Accept these fields in natural language or JSON:

- `budget`: required, in RMB. Spend at most this amount; use only complete 2 RMB lines unless the selected game has a different current price.
- `game`: `auto`, `ssq`, `dlt`, `7lc`, `kl8`, `3d`, `pl3`, `pl5`, or `7xc`. If `auto`, choose from the risk profile but say that the choice is preference-based unless current official prize-pool and promotion data are available.
- `risk_profile`: `frequency`, `balanced`, or `tail`. Default to `balanced` only after confirming the user is comfortable with a negative expected return.
- `seed`: optional reproducibility seed. If absent, generate and display a seed so the result can be reproduced.
- `live_data`: optional official current pool, fixed prizes, promotion terms, sales, and winning-count data. Do not invent missing values.

If `budget` is missing, ask for it. If it is below one complete line, explain that no ticket can be generated. Keep leftover RMB visible rather than silently rounding up.

## Decision workflow

1. Parse the budget, game preference, risk profile, and any current official data.
2. For live or historical analysis, automatically run `scripts/official_data.py sync --games ...` first on every invocation; the default is to fetch all currently available official history, merge it into a local cache, and deduplicate by issue. Users do not need to choose a count or data directory. It validates every record and stores source URL, retrieval time, and raw-response hash. If a source fails, report the failure; do not silently switch to a third-party history file or silently present an old cache as current.
   - Choose the history window automatically: use all available records as the main descriptive sample, compare recent 100 and recent 500 draws when available, and label the sample as insufficient (<100), limited (100–499), or adequate for descriptive statistics (≥500). This is a data-quality policy, not evidence that older draws predict future draws.
   - Read the latest verified issue from the fresh snapshot and use it as the reservation namespace for this draw.
3. Verify rule-sensitive facts against current official lottery sources when making a live recommendation. Use `references/rules.md` as a source registry, not as permission to assume the rules have not changed.
4. Select a game. Without live pool/promotion data, label the result `no_live_edge_established`; never call a game “best” merely because its jackpot is larger or its hit frequency is higher.
5. Compute exact base probabilities for the selected game. For digital lotteries, separate jackpot probability, any-prize probability when calculable, and theoretical return from actual net return.
6. Allocate only the stated budget. Generate distinct combinations where possible. For number games, use the helper in `scripts/lottery_engine.py`; its anti-crowd score is a heuristic for reducing likely shared jackpots, not a draw predictor.
   - Do not pass a fixed seed unless the user explicitly wants reproducibility. The same seed and inputs intentionally reproduce the same combinations.
   - Use the built-in shared reservation service at `https://lottery-quant-reservations.lee226520.chatgpt.site` with the latest official draw issue passed to `--draw-issue`; reserve each generated line. A reservation conflict must regenerate the line; service failure must be reported rather than hidden. Users do not configure this URL.
7. If live data is supplied, calculate tax-aware expected payout using the current game rule and the portfolio as a whole. Model shared prizes as a distribution, not a single point estimate. If live data is absent, report `EV_unverified` and do not fabricate a percentage.
8. Return a compact report with: selected game and reason, budget/spend/leftover, seed, combinations, odds, coverage, assumptions, data timestamp, and responsible-play warning.
   - Always include `数理分析`: exact combination-space formula, portfolio coverage probability, selected-line count, unique-number coverage, sum/odd-even/zone diagnostics, and the expected baseline for any historical frequency comparison.
   - Always include `选号逻辑`: budget constraint, within-portfolio de-duplication, shared reservation status, and the anti-crowd heuristic actually applied. Say explicitly that historical frequency/omission values were not used as predictive weights unless a separately validated model is requested.

## What “automatic selection” means

Automatic selection means generating combinations for the user to review and purchase through a lawful physical channel. It does not mean buying or submitting a ticket. For `ssq`, `dlt`, and `7lc`, use distinct combinations and a mild anti-crowd heuristic: avoid obvious birthday-only sets, long runs, repeated endings, and visually patterned lines. State clearly that this may affect shared-prize risk only if the heuristic matches actual player behavior; it cannot affect the draw.

For `kl8`, choose the number count by profile only as a risk-shape choice: `frequency` favors 1–2 numbers, `balanced` favors 5–6, and `tail` favors 9–10. Do not describe any count as more profitable without current rule and promotion data.

For `3d`, `pl3`, `pl5`, and `7xc`, number generation is only a reproducible random selection. Do not use hot/cold numbers, omission counts, or historical patterns as predictive features.

## Cross-user duplicate control

The default standalone mode provides local uniqueness only: no repeated line inside one response, a fresh random seed when the user does not supply one, and a mild anti-crowd heuristic. It cannot guarantee that two separate users will never receive the same line.

For a hosted multi-user deployment that wants a stronger guarantee, add a small shared reservation API keyed by `(draw_issue, game, normalized_combination_hash)` with an atomic unique constraint. Store only the hash and expiry time, not the user identity or ticket details. On a conflict, regenerate that line; expire reservations after the draw. If the service is unavailable, fall back to standalone mode and label the result `global_uniqueness_unverified` rather than pretending it is unique.

## Output language

Prefer wording such as:

> 在预算 100 元内生成 50 注；这不改变单注开奖概率，也没有验证出正EV。以下组合仅用于减少明显撞号模式，不能提高中奖率。

When the user asks for “正EV”, require official current rule/pool/promotion inputs and show the break-even calculation. A nominal return rate below 100% is not positive EV. Tax applies to the relevant aggregated computer-lottery winnings, not independently to every line.

## Persuasive but honest analysis format

Users may want an analysis that feels substantial and decision-ready. Make it persuasive through auditability, not invented authority. Use these sections in order:

1. `决策结论`: selected game, spend, line count, and the single most important caveat.
2. `预算约束`: requested budget, actual spend, leftover, and why the system did not round up.
3. `玩法筛选`: compare the selected game with one or two alternatives using stable facts and clearly mark any missing live data.
4. `概率计算`: show the combination-space formula and the one-line and portfolio probabilities.
5. `组合策略`: explain coverage, duplicate avoidance, and the anti-crowd heuristic; explicitly state what this cannot change.
6. `EV与税务`: show either the verified calculation or `EV_unverified` with the missing inputs.
7. `执行清单`: print the combinations and the seed so the result is reproducible.

For a digital lottery portfolio, also print these calculated diagnostics rather than vague confidence language: front-area unique coverage, back-area unique coverage, pairwise overlap summary, front-sum range/mean, odd-even distribution, zone distribution, and the exact anti-crowd score definition. Compare historical frequencies with the uniform baseline `draw_count × picks_per_draw / number_range`; do not interpret deviations as signals.

Useful labels are `官方规则`, `精确计算`, `模型估计`, and `未验证假设`. Do not use fake confidence scores, fabricated backtests, invented “AI命中率”, or language implying that a random draw has been predicted.

## Supporting resources

- Run `scripts/official_data.py sync --games all --data-dir ./data` to backfill all currently available official records for all supported games. Add `--count N` only for an explicit technical override; `--count 0` means all available pages.
- Run `scripts/official_data.py analyze --game ssq --data-dir ./data` to let the analyzer choose the window automatically and report the 100/500/all comparison.
- Run `scripts/lottery_engine.py` for deterministic budget allocation and combination generation.
- Read `references/rules.md` when checking current rule versions, official sources, tax, or compliance boundaries.
- Read `references/methodology.md` when explaining EV, shared-prize modeling, coverage, or the limits of the crowd model.
- For a multi-user deployment, read `services/README.md` and run `services/reservation_server.py` behind HTTPS with persistent storage.
