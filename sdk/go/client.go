// Package gramrail connects existing Go applications to the GramRail runtime.
package gramrail

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

type APIError struct {
	Status  int
	Code    string
	Message string
}

func (e *APIError) Error() string { return e.Message }

type Job struct {
	ID          string         `json:"id"`
	BotID       string         `json:"bot_id"`
	Kind        string         `json:"kind"`
	Payload     map[string]any `json:"payload"`
	State       string         `json:"state"`
	Attempts    int            `json:"attempts"`
	MaxAttempts int            `json:"max_attempts"`
	LeaseToken  string         `json:"lease_token"`
	LeaseUntil  *float64       `json:"lease_until"`
	Result      map[string]any `json:"result"`
	Progress    map[string]any `json:"progress"`
	Error       *string        `json:"error"`
}

type Client struct {
	baseURL string
	apiKey  string
	http    *http.Client
}

func NewClient(baseURL, apiKey, botID string, transport *http.Client) (*Client, error) {
	u, err := url.Parse(baseURL)
	if err != nil || u.Hostname() == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("provide an http(s) runtime URL without credentials, query, or fragment")
	}
	if u.Scheme == "http" && u.Hostname() != "localhost" && u.Hostname() != "127.0.0.1" && u.Hostname() != "::1" {
		return nil, errors.New("non-local runtime connections require HTTPS")
	}
	if apiKey == "" || !regexp.MustCompile(`^[a-z][a-z0-9_-]{0,63}$`).MatchString(botID) {
		return nil, errors.New("a valid bot ID and API key are required")
	}
	h := http.Client{Timeout: 15 * time.Second}
	if transport != nil {
		h = *transport
	}
	if h.Timeout == 0 {
		h.Timeout = 15 * time.Second
	}
	h.CheckRedirect = func(req *http.Request, via []*http.Request) error { return http.ErrUseLastResponse }
	return &Client{baseURL: strings.TrimRight(baseURL, "/") + "/api/v1/bots/" + url.PathEscape(botID), apiKey: apiKey, http: &h}, nil
}

func (c *Client) Request(ctx context.Context, method, path string, input, output any) error {
	var body io.Reader
	if input != nil {
		data, err := json.Marshal(input)
		if err != nil {
			return err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	const maximum = 4 << 20
	data, err := io.ReadAll(io.LimitReader(resp.Body, maximum+1))
	if err != nil {
		return err
	}
	if len(data) > maximum {
		return errors.New("GramRail response exceeds 4 MiB")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var envelope struct {
			Error struct {
				Code    string `json:"code"`
				Message string `json:"message"`
			} `json:"error"`
		}
		_ = json.Unmarshal(data, &envelope)
		if envelope.Error.Message == "" {
			envelope.Error.Message = "GramRail request failed"
		}
		if envelope.Error.Code == "" {
			envelope.Error.Code = "http_error"
		}
		return &APIError{Status: resp.StatusCode, Code: envelope.Error.Code, Message: envelope.Error.Message}
	}
	if output == nil {
		return nil
	}
	return json.Unmarshal(data, output)
}

func (c *Client) Enqueue(ctx context.Context, kind string, payload map[string]any, dedupeKey string) (*Job, error) {
	body := map[string]any{"kind": kind, "payload": payload}
	if payload == nil {
		body["payload"] = map[string]any{}
	}
	if dedupeKey != "" {
		body["dedupe_key"] = dedupeKey
	}
	var job Job
	err := c.Request(ctx, http.MethodPost, "/jobs", body, &job)
	if err != nil {
		return nil, err
	}
	return &job, nil
}

func (c *Client) Claim(ctx context.Context, kinds []string, leaseSeconds int) (*Job, error) {
	var job *Job
	err := c.Request(ctx, http.MethodPost, "/jobs/claim", map[string]any{"kinds": kinds, "lease_seconds": leaseSeconds}, &job)
	return job, err
}

func safeID(id string) (string, error) {
	if id == "" || id == "." || id == ".." {
		return "", errors.New("a nonempty resource ID is required")
	}
	return url.PathEscape(id), nil
}

func (c *Client) Complete(ctx context.Context, id, leaseToken string, result map[string]any) (*Job, error) {
	escaped, err := safeID(id)
	if err != nil {
		return nil, err
	}
	if result == nil {
		result = map[string]any{}
	}
	var job Job
	err = c.Request(ctx, http.MethodPost, fmt.Sprintf("/jobs/%s/complete", escaped), map[string]any{"lease_token": leaseToken, "result": result}, &job)
	if err != nil {
		return nil, err
	}
	return &job, nil
}

func (c *Client) SendText(ctx context.Context, chatID int64, text, dedupeKey string) (*Job, error) {
	body := map[string]any{"chat_id": chatID, "text": text}
	if dedupeKey != "" {
		body["dedupe_key"] = dedupeKey
	}
	var job Job
	err := c.Request(ctx, http.MethodPost, "/messages", body, &job)
	if err != nil {
		return nil, err
	}
	return &job, nil
}
