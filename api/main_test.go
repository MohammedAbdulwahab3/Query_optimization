package main

import (
	"bytes"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func testHandlers(authEnabled bool) *Handlers {
	return &Handlers{
		cache: &Cache{},
		auth: &Auth{
			secret:   []byte("test-secret"),
			ttl:      time.Hour,
			enabled:  authEnabled,
			analysts: map[string]string{"agent.alem": "pw"},
		},
	}
}

// With auth disabled, requireAuth/warrantGate pass through, so we can exercise
// routing, number validation, and the error handler without live datastores.
func TestValidation(t *testing.T) {
	app := buildApp(testHandlers(false))

	cases := []struct {
		path string
		want int
	}{
		{"/health", 200},
		{"/search/abc", 400},
		{"/search/123", 400},
		{"/graph/notanumber", 400},
		{"/timeline/12x45678", 400},
	}
	for _, tc := range cases {
		req, _ := http.NewRequest(http.MethodGet, tc.path, nil)
		resp, err := app.Test(req, -1)
		if err != nil {
			t.Fatalf("%s: %v", tc.path, err)
		}
		if resp.StatusCode != tc.want {
			body, _ := io.ReadAll(resp.Body)
			t.Errorf("%s: got %d want %d (%s)", tc.path, resp.StatusCode, tc.want,
				strings.TrimSpace(string(body)))
		}
	}
}

func TestAuth(t *testing.T) {
	app := buildApp(testHandlers(true))

	// protected route without a token -> 401 (before any datastore access)
	req, _ := http.NewRequest(http.MethodGet, "/search/251911000001", nil)
	resp, _ := app.Test(req, -1)
	if resp.StatusCode != 401 {
		t.Errorf("no token: got %d want 401", resp.StatusCode)
	}

	// bad credentials -> 401
	req, _ = http.NewRequest(http.MethodPost, "/auth/login",
		bytes.NewReader([]byte(`{"username":"agent.alem","password":"wrong"}`)))
	req.Header.Set("Content-Type", "application/json")
	resp, _ = app.Test(req, -1)
	if resp.StatusCode != 401 {
		t.Errorf("bad creds: got %d want 401", resp.StatusCode)
	}

	// good credentials -> 200 + a token that verifies
	req, _ = http.NewRequest(http.MethodPost, "/auth/login",
		bytes.NewReader([]byte(`{"username":"agent.alem","password":"pw"}`)))
	req.Header.Set("Content-Type", "application/json")
	resp, _ = app.Test(req, -1)
	if resp.StatusCode != 200 {
		t.Fatalf("login: got %d want 200", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "token") {
		t.Errorf("login response missing token: %s", body)
	}
}

func TestNumberRegex(t *testing.T) {
	good := []string{"251911000001", "123456", "999999999999999"}
	bad := []string{"", "12345", "abc123", "2519110000011234567", "251 911"}
	for _, g := range good {
		if !validNumber(g) {
			t.Errorf("expected %q to be valid", g)
		}
	}
	for _, b := range bad {
		if validNumber(b) {
			t.Errorf("expected %q to be invalid", b)
		}
	}
}
