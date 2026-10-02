# Methodology

## Probability

For a fixed combination, use the current official rule. For simple distinct-line coverage, the jackpot probability for `m` distinct lines is `m / Ω`, where `Ω` is the complete combination space, provided `m <= Ω`. This is coverage, not prediction.

The helper currently records these base spaces:

- 双色球: `C(33, 6) × 16 = 17,721,088`.
- 大乐透: `C(35, 5) × C(12, 2) = 21,425,712`.
- 七乐彩: `C(30, 7) = 2,035,800`.
- 福彩3D / 排列3: `1,000` exact ordered outcomes.
- 排列5: `100,000` exact ordered outcomes.
- 7星彩: `1,000,000 × 15 = 15,000,000` under the current six-digit-plus-0–14 structure.

## EV

For a portfolio, define:

`EV_net = E(after-tax prize receipts, including shared-prize distribution) - ticket cost`.

Do not estimate a floating prize with `pool / expected winners` alone when the user buys multiple lines. The user’s own winning lines change the winner count and may share the same draw. Use a joint simulation over draw outcomes, other-player ticket counts, fixed-prize limits, caps, promotions, and tax aggregation.

If any of those inputs are missing, report `EV_unverified`; do not convert a nominal advertised prize into a claimed return rate.

## Crowd model

The anti-crowd selector is deliberately heuristic. It penalizes birthday-only sets, long consecutive runs, repeated endings, and visual patterns. It is not trained on official ticket-level purchase data and must never be described as a calibrated probability of another player choosing a line.

If a future version receives reliable ticket-level choice data, fit a calibrated distribution over combinations and publish validation metrics. Report uncertainty, because a lower estimated crowd score does not guarantee a smaller shared prize.

## Portfolio objectives

“Optimal” is incomplete unless the objective is specified. Possible objectives include:

- maximize probability of at least one prize;
- maximize probability of recovering at least a stated amount;
- minimize overlap among lines;
- maximize a lower-tail metric such as CVaR;
- maximize expected after-tax payout under a verified promotion.

Never silently replace one objective with another. A portfolio can improve the chance of a small win while leaving expected net return negative.
