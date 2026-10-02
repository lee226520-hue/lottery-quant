# Shared reservation service

This optional service prevents duplicate combinations across multiple Skill
installations for the same draw issue and game. It stores only a SHA-256 hash
and expires reservations after 48 hours.

The shared deployment used by the packaged Skill is:

`https://lottery-quant-reservations.lee226520.chatgpt.site`

Run locally:

```bash
python3 services/reservation_server.py --host 127.0.0.1 --port 8787 --db ./data/reservation.sqlite3
```

Use it from the generator:

```bash
LOTTERY_RESERVATION_URL=http://127.0.0.1:8787 \
python3 scripts/lottery_engine.py \
  --game dlt --budget 20 --draw-issue 26112 --json
```

The generator submits a batch of candidate lines in one request, so normal
users do not wait for one network round-trip per line.

For a real multi-user deployment, put the service behind HTTPS, rate limiting,
and a persistent disk. The reservation key is `(draw_issue, game,
combination_hash)` and the database primary key makes the check-and-reserve
operation atomic. If the service is not reachable, the client fails rather
than claiming global uniqueness.
