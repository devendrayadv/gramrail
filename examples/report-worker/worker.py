"""A finite worker example. It never sends Telegram messages or modifies webhooks."""
import os

from gramrail.client import Client


def main() -> None:
    key = os.environ.get("GRAMRAIL_BOT_KEY")
    if not key:
        raise SystemExit("Set GRAMRAIL_BOT_KEY to the runtime key first.")
    with Client(os.environ.get("GRAMRAIL_URL", "http://127.0.0.1:8080"), key,
                os.environ.get("GRAMRAIL_BOT_ID", "demo")) as rail:
        job = rail.enqueue("reports.generate", {"report_id": "example-1"},
                           dedupe_key="example-report-1")
        claimed = rail.claim(["reports.generate"], lease_seconds=30)
        if claimed is None:
            print("No eligible job. Existing report status:", rail.get_job(job["id"])["state"])
            return
        rail.heartbeat(claimed["id"], claimed["lease_token"], progress={"step": "render"})
        report_id = str(claimed["payload"].get("report_id", "unknown"))
        rail.complete(claimed["id"], claimed["lease_token"],
                      {"report_id": report_id, "summary": "Example report generated."})
        print("Completed:", claimed["id"])


if __name__ == "__main__":
    main()
