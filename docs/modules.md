# Reusable modules

Two built-ins are implemented: `forms` and `approvals`. This is not yet a
third-party plugin registry. Their manifests in `modules/manifest.py` describe
dependencies and capabilities; they do not grant an operating-system sandbox.

## Forms

Configure forms on each bot. A form has a stable `name`, title, ordered fields,
and expiry interval. Fields support `text`, `integer`, `url`, and `choice`.
Choices are explicit strings; text lengths can be constrained, and integers must fit the portable JSON range.
The model validates duplicate names and invalid bounds before startup.

Users start with `/submit` or `/submit form-name`, answer each question, use
`/back` to revisit the previous field, and `/cancel` to stop. Editing an earlier
answer clears dependent later answers. An active form must be cancelled or completed before another can start
in the same bot/chat/user scope. State survives a restart.

An HTTP URL field is validated but never fetched. URL acceptance does not mean
its destination is trustworthy. An application that fetches user URLs must add
SSRF protection, resource limits, and destination policy.

## Approvals

Approvals depends on forms. Configure trusted `admin_ids` and a `review_chat_id`.
On form completion the router creates a pending workflow and a review message.
Approve/reject callback data contains a workflow reference, not authorization.
Every callback checks the Telegram user ID against the configured administrators.

Approval/rejection changes workflow state and queues a notification to the
submitter. It does **not** automatically publish a directory entry or copy a
file to a channel. Add your business integration deliberately. For atomic
transition-triggered custom jobs, use the WorkflowEngine signal/effect API.

A saved approval and a failed notification are separate facts. Inspect workflow
state and delivery jobs rather than assuming a failed message rolled back the
approval. Repeated decisions return an already-decided response.

## Extending the foundation

An application may compose the public `Forms`, `WorkflowEngine`, `JobQueue`, and
HTTP APIs today. Adding a new built-in requires input models, dependency metadata,
configuration validation, authorization tests, negative/retry tests, and docs.

A future public plugin API will need versioned hooks, schema upgrades, controlled
capabilities, and compatibility tests. Do not advertise an arbitrary folder of
Python code as an isolated or safely permission-limited extension.
