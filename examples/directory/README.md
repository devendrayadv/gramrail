# Directory submissions

A complete reusable-forms-and-approvals example. It collects a title and URL;
reviewers accept or reject the submission. It does not crawl the submitted URL,
publish a website, or claim that a listed bot is safe.

From the repository, after installing GramRail:

```bash
cd examples/directory
gramrail dev --config gramrail.json
```

Open the displayed console and paste its temporary development key. As user
1001, send `/submit`, then a title, then an HTTPS URL. Switch to reviewer ID 1
and select Approve or Reject. Inspect the recorded decision and queued messages.

The reviewer IDs are simulation defaults. Replace `admin_ids` and
`review_chat_id` before connecting a real Telegram bot. See the root getting
started guide for explicit live configuration. Repeated decisions do not create
another accepted transition, but external notifications do not have an
exactly-once guarantee.
