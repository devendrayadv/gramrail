package gramrail

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnqueue(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Error("missing authorization")
		}
		if r.URL.Path != "/api/v1/bots/demo/jobs" {
			t.Error("wrong bot scope")
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(202)
		_, _ = w.Write([]byte(`{"id":"one","state":"queued"}`))
	}))
	defer server.Close()
	client, err := NewClient(server.URL, "test-key", "demo", nil)
	if err != nil {
		t.Fatal(err)
	}
	job, err := client.Enqueue(context.Background(), "work", map[string]any{"x": 1}, "one")
	if err != nil || job.ID != "one" {
		t.Fatalf("unexpected result: %v %v", job, err)
	}
}

func TestEmptyClaim(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = w.Write([]byte(`null`)) }))
	defer server.Close()
	client, _ := NewClient(server.URL, "key", "demo", nil)
	job, err := client.Claim(context.Background(), []string{"work"}, 30)
	if err != nil || job != nil {
		t.Fatal("expected an empty claim")
	}
}

func TestConflict(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(409)
		_, _ = w.Write([]byte(`{"error":{"code":"conflict","message":"Changed"}}`))
	}))
	defer server.Close()
	client, _ := NewClient(server.URL, "key", "demo", nil)
	_, err := client.Enqueue(context.Background(), "work", nil, "same")
	var apiError *APIError
	if !errors.As(err, &apiError) || apiError.Status != 409 || apiError.Code != "conflict" {
		t.Fatal("lost structured error")
	}
}

func TestUnsafeURLs(t *testing.T) {
	for _, address := range []string{"http://external.example", "https://user:pass@example.com", "file:///etc/passwd", "https://example.com?q=secret"} {
		if _, err := NewClient(address, "key", "demo", nil); err == nil {
			t.Errorf("accepted %s", address)
		}
	}
	if _, err := NewClient("https://runtime.example", "key", "..", nil); err == nil {
		t.Error("accepted traversal")
	}
}

func TestRedirectsNeverForwardCredentials(t *testing.T) {
	called := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { called = true }))
	defer target.Close()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, target.URL, 307) }))
	defer server.Close()
	client, _ := NewClient(server.URL, "key", "demo", nil)
	_, err := client.Enqueue(context.Background(), "work", nil, "")
	if err == nil || called {
		t.Fatal("followed an unsafe redirect")
	}
}
