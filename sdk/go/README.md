# GramRail Go client

A standard-library-only HTTP client. Module path:
`github.com/devendrayadv/gramrail/sdk/go`. For development against this checkout, use a
local replace directive in your consuming project's go.mod:

```text
require github.com/devendrayadv/gramrail/sdk/go v0.0.0
replace github.com/devendrayadv/gramrail/sdk/go => /absolute/path/to/gramrail/sdk/go
```

```go
client, err := gramrail.NewClient("http://127.0.0.1:8080", apiKey, "demo", nil)
if err != nil {
    return err
}
job, err := client.Enqueue(ctx, "reports.generate", map[string]any{
    "report_id": "r-1",
}, "r-1")
if err != nil {
    return err
}
fmt.Println(job.ID)
```

Import `gramrail "github.com/devendrayadv/gramrail/sdk/go"`. Keep keys in a trusted
backend, and use HTTPS outside localhost. A context controls cancellation.
The client refuses redirects, including when an HTTP client is injected.

Helpers currently cover `Enqueue`, `Claim`, `Complete`, and `SendText`.
`Request(ctx, method, path, input, output)` accesses heartbeat, failure, workflow,
and inspection endpoints using the [API contract](../../docs/api.md). This is
not a claim of helper-method parity with every other SDK. No writes are
silently retried. Claims may return nil when no eligible work exists.

```bash
cd sdk/go
go test -race ./...
go vet ./...
```
