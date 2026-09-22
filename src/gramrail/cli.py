"""Small, explicit commands. No command silently rewires Telegram delivery."""
import argparse
import json
import os
import secrets
import sqlite3
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .adapters.bot_api import BotAPI, TelegramFailure
from .config import Config, save, starter
from .errors import InvalidInput, RailError
from .modules.manifest import MODULES, resolve
from .store import Store
from .telegram import TelegramRouter


def initialize(path: Path) -> None:
    if path.exists():
        raise InvalidInput("Choose a new directory. GramRail will not overwrite an existing project.")
    name = path.name.lower().replace("_", "-")
    value = starter(name)
    Config.model_validate(value)
    path.mkdir(parents=True)
    save(value, path / "gramrail.json")
    (path / ".env.example").write_text(
        "# Copy values into your shell or process manager. This file is not loaded automatically.\n"
        "GRAMRAIL_ADMIN_KEY=replace-with-at-least-32-random-characters\n"
        "GRAMRAIL_BOT_KEY=replace-with-a-different-random-key\n"
        "TELEGRAM_BOT_TOKEN=replace-with-your-test-bot-token\n"
        "TELEGRAM_WEBHOOK_SECRET=replace-with-a-random-webhook-secret\n")
    (path / ".gitignore").write_text(".env\n.gramrail/\n__pycache__/\n.pytest_cache/\n")
    (path / "README.md").write_text(
        "# " + name + "\n\nRun `gramrail dev` for a local, offline simulation.\n"
        "Open the displayed console address and paste the temporary development key.\n\n"
        "For Telegram: edit admin_ids and review_chat_id in gramrail.json, set the\n"
        "environment variables listed in .env.example, then run `gramrail doctor`.\n"
        "Use `gramrail serve --live` only when ready to send real messages.\n"
        "The runtime never automatically sets or deletes a webhook.\n")
    (path / "tests").mkdir()
    (path / "tests/test_config.py").write_text(
        "from pathlib import Path\nfrom gramrail.config import Config\n\n\n"
        "def test_config():\n    config = Config.load(Path(__file__).parents[1] / 'gramrail.json')\n"
        "    assert config.bots\n")
    print(f"Created {path}. Next: cd {path} && gramrail dev")


def doctor(config: Config, telegram: bool = False) -> list[dict[str, str]]:
    checks = [{"status": "ok", "check": "configuration", "message": f"{len(config.bots)} bot(s); module dependencies resolved."}]
    try:
        config.credentials(live=False)
        checks.append({"status": "ok", "check": "api_keys", "message": "Configured keys meet minimum length and separation requirements."})
    except RailError as exc:
        checks.append({"status": "warning", "check": "api_keys", "message": str(exc)})
    database = Path(config.database)
    if not database.exists():
        checks.append({"status": "info", "check": "database", "message": "Database does not exist; it will be created when the runtime starts."})
    else:
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            checks.append({"status": "ok" if integrity == "ok" else "error", "check": "database", "message": "SQLite quick_check: " + integrity})
        finally:
            conn.close()
    if telegram:
        for bot in config.bots:
            token = os.environ.get(bot.token_env)
            if not token:
                checks.append({"status": "warning", "check": bot.id, "message": f"Missing {bot.token_env}; Telegram checks skipped."})
                continue
            api = BotAPI(token)
            try:
                api.call("getMe", {})
                webhook = api.call("getWebhookInfo", {})
                configured = bool(webhook.get("url"))
                checks.append({"status": "info", "check": bot.id + ".delivery", "message": (
                    "A webhook is configured. Long polling must not start. No settings were changed."
                    if configured else "No webhook is configured. This does not prove whether another polling process is running.")})
                if webhook.get("pending_update_count", 0):
                    checks.append({"status": "warning", "check": bot.id + ".backlog", "message": f"{webhook['pending_update_count']} pending Telegram updates."})
            except TelegramFailure as exc:
                checks.append({"status": "error", "check": bot.id + ".telegram", "message": exc.code})
            finally:
                api.close()
    return checks


def poll(config: Config, bot_id: str, *, once: bool = False) -> None:
    bot = config.bot(bot_id)
    token = os.environ.get(bot.token_env)
    if not token:
        raise InvalidInput(f"Set {bot.token_env} first.")
    api = BotAPI(token)
    try:
        info = api.call("getWebhookInfo", {})
        if info.get("url"):
            raise InvalidInput("A webhook is active. Polling refused; no webhook was deleted.")
        router = TelegramRouter(Store(config.database), config)
        print("Polling selected bot. Run the live API runtime separately to drain its delivery queue.", flush=True)
        while True:
            updates = api.call("getUpdates", {"offset": router.offset(bot_id), "timeout": 25,
                                               "allowed_updates": ["message", "callback_query"]}, timeout=35)
            if not isinstance(updates, list):
                raise InvalidInput("Telegram returned an invalid update batch.")
            for update in updates:
                router.ingest(bot_id, update)
                router.save_offset(bot_id, update["update_id"] + 1)
            if once:
                return
    finally:
        api.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gramrail", description="Reusable Telegram features, durable jobs, and a safe local simulator.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new bot project without overwriting files.")
    init.add_argument("path", type=Path)
    add = commands.add_parser("add", help="Enable built-in modules and their requirements.")
    add.add_argument("modules", nargs="+", choices=list(MODULES))
    add.add_argument("--config", default="gramrail.json", type=Path)
    add.add_argument("--bot", required=True)
    dev = commands.add_parser("dev", help="Start an offline simulator and console on localhost.")
    dev.add_argument("--config", type=Path)
    dev.add_argument("--port", type=int, default=8080)
    serve = commands.add_parser("serve", help="Start the runtime with real Telegram delivery explicitly enabled.")
    serve.add_argument("--config", default="gramrail.json", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--live", action="store_true", required=True)
    diagnose = commands.add_parser("doctor", help="Inspect configuration; never changes Telegram settings.")
    diagnose.add_argument("--config", default="gramrail.json", type=Path)
    diagnose.add_argument("--telegram", action="store_true", help="Also call getMe and getWebhookInfo.")
    polling = commands.add_parser("poll", help="Receive updates; refuses to run with an active webhook.")
    polling.add_argument("--config", default="gramrail.json", type=Path)
    polling.add_argument("--bot", required=True)
    polling.add_argument("--live", action="store_true", required=True)
    backup = commands.add_parser("backup", help="Create a new consistent SQLite backup without overwriting files.")
    backup.add_argument("--config", default="gramrail.json", type=Path)
    backup.add_argument("output", type=Path)
    test = commands.add_parser("test", help="Run local pytest in the current project; never uses GitHub Actions.")
    test.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize(args.path)
        elif args.command == "add":
            value = json.loads(args.config.read_text())
            bot = next((bot for bot in value["bots"] if bot["id"] == args.bot), None)
            if bot is None:
                raise InvalidInput("Unknown bot in configuration.")
            bot["modules"] = [module.name for module in resolve([*bot.get("modules", []), *args.modules])]
            save(value, args.config)
            print("Enabled: " + ", ".join(bot["modules"]))
        elif args.command in ("dev", "serve"):
            import uvicorn
            from .api import create_app
            if args.command == "dev":
                path = args.config or Path("gramrail.json")
                config = Config.load(path) if path.exists() else Config.model_validate(starter("demo"))
                config.database = str(Path.cwd() / ".gramrail" / "simulation.sqlite")
                key = secrets.token_urlsafe(32)
                app = create_app(config, credentials={config.admin_key_env: key})
                print(f"Simulation only. No Telegram calls.\nConsole: http://127.0.0.1:{args.port}/console\nTemporary development key: {key}", flush=True)
                uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
            else:
                config = Config.load(args.config)
                app = create_app(config, live=True)
                print("Live delivery enabled. Existing webhook settings are unchanged.", flush=True)
                uvicorn.run(app, host=args.host, port=args.port)
        elif args.command == "doctor":
            checks = doctor(Config.load(args.config), telegram=args.telegram)
            for check in checks:
                print(f"{check['status'].upper():7} {check['check']}: {check['message']}")
            return 1 if any(check["status"] == "error" for check in checks) else 0
        elif args.command == "poll":
            poll(Config.load(args.config), args.bot)
        elif args.command == "backup":
            config = Config.load(args.config)
            if not Path(config.database).is_file():
                raise InvalidInput("Database does not exist; no empty backup was created.")
            print(Store(config.database).backup(args.output))
        elif args.command == "test":
            return subprocess.run([sys.executable, "-m", "pytest", *args.args], check=False).returncode
    except KeyboardInterrupt:
        return 130
    except (RailError, ValidationError, OSError, ValueError, TelegramFailure) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
