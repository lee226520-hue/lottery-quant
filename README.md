# 彩票官方数据与预算选号（lottery-quant）

面向中国大陆主流数字彩票的 Codex Skill：每次联网调用官方数据，在固定预算内生成可复现、可解释的组合，并展示概率、预算、规则假设和风险边界。

它不预测开奖号码、不承诺盈利、不购票、不代购、不收款，也不自动投注。

## 最简单的用法

把整个 lottery-quant 文件夹复制到 Codex skills 目录，然后直接说：

$lottery-quant 我有20元，想买大乐透，联网回溯后给我一份选号报告。

使用者只需要给预算和玩法，不需要填写多少期、数据存在哪里或选择统计方法。每次使用都会访问官方接口，自动比较全量历史、最近100期和最近500期；第一次同步可能较慢，之后按期号增量更新。

这里的“实时”指每次使用时联网更新，不是后台24小时监控。官方接口不可用时会明确提示数据无法验证，不会把旧缓存伪装成最新数据。

## 支持的玩法

双色球、七乐彩、快乐8、福彩3D、超级大乐透、排列3、排列5、7星彩，以及 auto 自动选择玩法。

## 直接运行

先同步官方全量历史：

python3 scripts/official_data.py sync --games all --count 0 --data-dir ./data

查看分析：

python3 scripts/official_data.py analyze --game ssq --data-dir ./data

预算选号：

python3 scripts/lottery_engine.py --game dlt --budget 20 --risk-profile balanced --json

## 分析过程

输出不只给号码，还会展示组合空间公式、预算覆盖概率、前后区覆盖数、和值与奇偶分布、组合之间的重叠、历史频次均匀基线，以及实际使用的反撞号规则。热冷号和遗漏只描述过去，不包装成预测能力。

预算按官方票价换算；组合不重复；使用新的随机 seed；通过反人群启发式降低生日号、整十号、连续号等常见选择造成的撞号概率。中奖概率仍由官方组合空间决定。

## 多用户共享去重

Skill 已内置共享 HTTPS 服务：

https://lottery-quant-reservations.lee226520.chatgpt.site

它按开奖期号、玩法和号码哈希做原子登记，48小时后过期，只保存哈希，不保存用户身份。使用者不需要注册、登录或配置 URL；服务不可用时客户端会失败，不会假装实现全局唯一。

如需自建服务，可运行：

python3 services/reservation_server.py --host 127.0.0.1 --port 8787 --db ./data/reservation.sqlite3

## 重要说明

历史回测不是预测模型，不能证明下一期有优势。动态 EV 需要奖池、派奖、共奖人数和税务情景，缺失数据时只输出 EV_unverified。请通过合法实体渠道购票，理性娱乐。

MIT License。
