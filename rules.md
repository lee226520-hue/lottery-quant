# Rule and source registry

This file is a source registry, not a guarantee that a rule is still current. Before a live recommendation, check the latest official announcement and record the retrieval date in the report.

## Official sources

- [Finance Ministry: 2026 lottery market closure](https://zhs.mof.gov.cn/zhengcefabu/202512/t20251225_3980205.htm) — 1–4 October 2026 closure; instant tickets may follow local arrangements.
- [Finance Ministry: 2026 Double Chromosphere rule approval](https://www.mof.gov.cn/gp/xxgkml/zhs/202601/t20260116_3982040.htm) — rule change approved; operational details should be checked against the current China Welfare Lottery rule.
- [China Welfare Lottery Double Chromosphere rules](https://www.gdfc.org.cn/resource/2026/2026011601.pdf) — 33 red numbers, 16 blue numbers, current prize conditions including 福运奖.
- [Finance Ministry: 2026 Super Lotto rule approval](https://www.mof.gov.cn/gp/xxgkml/zhs/202601/t20260116_3982041.htm) — rule change approval.
- [China Sports Lottery Super Lotto rules](https://m.lottery.gov.cn/ksjz/m/yxgz_dlt/) — 5/35 plus 2/12, current prize tiers and 8亿元 threshold.
- [Finance Ministry: 2026 Happy 8 rule approval](https://zhs.mof.gov.cn/zhengcefabu/202512/t20251219_3979617.htm) — changed fixed prizes, floating prizes, pools, and return-fund proportions.
- [Lottery tax announcement](https://m.lottery.gov.cn/xxgk/fg/zcfg/20240816/10044631.html) — same person, same draw, same game computer-lottery winnings are aggregated; winnings above 10,000 RMB are taxable at the applicable accidental-income rate.
- [Internet lottery sales notice](https://www.mof.gov.cn/gp/xxgkml/zhs/201808/t20180821_2994396.htm) — unauthorized internet lottery sales are prohibited.

## Runtime official data endpoints

The `scripts/official_data.py` adapter uses these endpoints at runtime:

- Welfare lottery: `https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice` with `name=ssq`, `qlc`, `kl8`, or `3d`. It first obtains a session cookie from the corresponding official results page.
- Sports lottery: `https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry` with `gameNo=85` for大乐透, `35` for排列3, `350133` for排列5, and `04` for7星彩.

The adapter does not use unofficial fallback history sources. If an official endpoint is unavailable or changes shape, the sync command fails loudly and preserves the last verified local snapshot.

## Data freshness rules

Treat game rules, prize tables, jackpot thresholds, promotions, market closures, sales, and winning counts as time-sensitive. A live report must include:

1. source URL or official bulletin identifier;
2. retrieval timestamp in Asia/Shanghai;
3. rule version or effective draw number;
4. whether the value is an official figure, a model estimate, or an unverified assumption.

Do not fill missing pool, promotion, or crowd data with plausible-looking numbers.
