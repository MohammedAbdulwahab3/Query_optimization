package main

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

// These tests exercise the HTTP layer — routing, the auth-stub middleware,
// number validation, and the error handler — without any live datastore.
// Invalid numbers are rejected before any store access, so nil stores are safe
// here; the cache with a nil Redis client degrades to a no-op.
func TestValidation(t *testing.T) {
	app := buildApp(&Handlers{cache: &Cache{}})

	cases := []struct {
		path string
		want int
	}{
		{"/health", 200},
		{"/search/abc", 400},       // non-numeric
		{"/search/123", 400},       // too short (<6 digits)
		{"/graph/notanumber", 400}, // non-numeric
		{"/timeline/12x45678", 400},
	}
	for _, tc := range cases {
		req := httptest_NewRequest(tc.path)
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

func httptest_NewRequest(path string) *http.Request {
	req, _ := http.NewRequest(http.MethodGet, path, nil)
	return req
}
