# Report worker

Demonstrates enqueue, claim, heartbeat/progress, and saved completion through the
Python SDK. This intentionally generates only an in-memory example result, not
a real report file or an external side effect.

In one terminal, start `gramrail dev`. In another, set `GRAMRAIL_BOT_KEY` to the
temporary key printed by the first terminal, then run from the repository root:

```bash
python examples/report-worker/worker.py
```

The default bot ID is `demo`. Set `GRAMRAIL_BOT_ID` and `GRAMRAIL_URL` for other
configured runtimes. Re-running uses the same enqueue key. Use an isolated demo
runtime: this worker can claim any eligible `reports.generate` job for its bot.

For actual slow work, heartbeat before the lease expires. A lost lease means
stop recording work with that token. External actions require their own
idempotency and reconciliation policy. This finite script is not a production
worker supervisor; job cancellation currently applies to queued jobs only.
