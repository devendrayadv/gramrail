# Getting started

GramRail has two different execution modes. `dev` is an offline simulation;
`serve --live` can send real Telegram messages. Never confuse the two.

## Install from the source checkout

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
gramrail --help
gramrail dev
```

Python 3.11+ is required. Development dependencies are optional when operating the
runtime: `python -m pip install -e .`. This project has not been uploaded to PyPI.
On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.

The console is at `http://127.0.0.1:8080/console`. Copy the temporary development
key printed in the terminal into the console. A reload discards the browser's
key; stopping and restarting `dev` generates a new key. The simulation database
persists at `.gramrail/simulation.sqlite` in the current working directory.

Send `/submit` as user 1001, then a title and an HTTPS URL. Change the simulated
user ID to 1 to approve. The simulator submits trusted test updates; it is not
an authentication mechanism for real Telegram users.

## Create a new application

```bash
gramrail init my-bot
cd my-bot
gramrail dev
gramrail test
```

`init` refuses to overwrite any existing directory. The generated configuration
contains a demo form, reviewer 1, and review chat 1. Those are simulation values,
not your actual Telegram identity. The generated test validates configuration.
`gramrail add approvals --bot my-bot` enables the built-in approvals module and
resolves its forms dependency. Third-party module installation is not implemented.

## Add to an existing bot

Keep your framework and business database. Choose an adoption boundary:

- Import `Store`, `JobQueue`, or `WorkflowEngine` on a single host.
- Call the bot-scoped HTTP API from Python, JavaScript, or Go.
- Forward complete updates only when you deliberately delegate their handling.

Do not pass a production update to both your own handler and the built-in router
unless you intend both sets of effects. A queue acknowledgement is not task
completion. See the [report worker](../examples/report-worker/README.md).

## Explicit live setup

Use a separate test bot first. Update `gramrail.json` with the actual administrator
user IDs, review chat ID, bot ID, forms, and environment variable names. Give the
bot access to the review destination; a private recipient must be reachable.

Generate independent runtime and webhook keys with a cryptographic generator:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `GRAMRAIL_ADMIN_KEY`, `GRAMRAIL_BOT_KEY`, `TELEGRAM_BOT_TOKEN`, and
`TELEGRAM_WEBHOOK_SECRET` through your shell or process manager. Use different
values for each key. Runtime keys are 24..256 printable, non-space ASCII
characters. The webhook secret permits letters, digits, underscore, and hyphen.
`.env` files are not loaded automatically. Do not put keys in source control,
URLs, shell command arguments, or screenshots.

```bash
gramrail doctor --config gramrail.json
gramrail doctor --config gramrail.json --telegram
gramrail serve --config gramrail.json --live
```

The live runtime will send queued Telegram messages. It does not register or
remove a webhook. Choose exactly one update ingress:

### Polling

In a second process on the same host, using the same configuration and database:

```bash
gramrail poll --config gramrail.json --bot my-bot --live
```

Polling refuses to start if Telegram reports a configured webhook. It never
deletes that webhook. A persistent cursor advances after the update transaction
commits. Run only one polling process per bot. Transient polling errors exit the
command; use a supervisor with bounded restart delay, and inspect repeated errors.

### Webhook

Put the runtime behind HTTPS and explicitly configure Telegram's `setWebhook`
method with your public `/webhooks/my-bot` URL, the configured `secret_token`, and
`allowed_updates` containing `message` and `callback_query`. Do this through a
trusted tool or script that does not log the bot token. Do not run polling for
that token at the same time. See the [Telegram Bot API](https://core.telegram.org/bots/api#setwebhook).

This release handles message text and callback buttons, not every Telegram update
type or media operation. Native Telegram Serverless is a separate experimental
integration described in [serverless.md](serverless.md).
