# Multiple bots

Two independently configured forms-and-approvals bots share one local runtime.
This tests shared code and separated bot records, not a complete support inbox.

```bash
cd examples/multi-bot
gramrail dev --config gramrail.json
```

Use the root development key in the console and switch bots. Bot `support-a`
uses reviewer 1; bot `support-b` uses reviewer 2. In live operation, set separate
bot API keys, Telegram tokens, and webhook secrets using the named environment
variables in the configuration. A bot key cannot access the other bot's API
records; the root key is intentionally authorized across both bots.

This is not automatic customer provisioning, staff-role management, or a
sandbox for mutually untrusted plugins. Replace demonstration administrator IDs
before live use. Both bots share a single-host SQLite failure domain.
