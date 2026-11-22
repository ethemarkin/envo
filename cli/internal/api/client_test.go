package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"envo/cli/internal/config"
)

// fakeServer accepts access token "fresh" and rotates refresh token "r1" -> "r2".
func fakeServer(t *testing.T, refreshCalls *int32) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/cli/auth/refresh", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(refreshCalls, 1)
		var body map[string]string
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["refresh_token"] != "r1" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"detail":"invalid_refresh_token"}`))
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": "fresh", "refresh_token": "r2", "expires_in": 900,
			"user": map[string]string{"email": "dev@example.com"},
		})
	})
	mux.HandleFunc("GET /api/auth/me", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer fresh" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"detail":"not_authenticated"}`))
			return
		}
		_, _ = w.Write([]byte(`{"id":"1","email":"dev@example.com"}`))
	})
	mux.HandleFunc("POST /api/projects/p/environments/e/import", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":"invalid_dotenv","errors":[{"line":2,"code":"invalid_key","message":"Invalid key: 1A"}]}`))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

func newStore(t *testing.T) config.FileStore {
	return config.FileStore{Path: filepath.Join(t.TempDir(), "credentials.json")}
}

func TestExpiredAccessTokenIsRefreshedAndSaved(t *testing.T) {
	var calls int32
	srv := fakeServer(t, &calls)
	store := newStore(t)
	creds := &config.Credentials{AccessToken: "stale", RefreshToken: "r1", AccessExpiresAt: time.Now().Add(-time.Minute)}

	c := New(srv.URL).WithCredentials(store, creds)
	me, err := c.Me(context.Background())
	if err != nil || me.Email != "dev@example.com" {
		t.Fatalf("me = %+v, err = %v", me, err)
	}
	if calls != 1 {
		t.Errorf("refresh calls = %d", calls)
	}
	saved, err := store.Load(srv.URL)
	if err != nil || saved.RefreshToken != "r2" || saved.AccessToken != "fresh" {
		t.Fatalf("saved = %+v, err = %v", saved, err)
	}
}

func TestUnauthorizedResponseTriggersOneRefresh(t *testing.T) {
	var calls int32
	srv := fakeServer(t, &calls)
	// Not expired locally, but rejected by the server (e.g. revoked).
	creds := &config.Credentials{AccessToken: "stale", RefreshToken: "r1", AccessExpiresAt: time.Now().Add(time.Hour)}
	c := New(srv.URL).WithCredentials(newStore(t), creds)
	if _, err := c.Me(context.Background()); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Errorf("refresh calls = %d", calls)
	}
}

func TestRevokedSessionClearsCredentials(t *testing.T) {
	var calls int32
	srv := fakeServer(t, &calls)
	store := newStore(t)
	creds := &config.Credentials{AccessToken: "stale", RefreshToken: "revoked", AccessExpiresAt: time.Now().Add(-time.Minute)}
	_ = store.Save(srv.URL, creds)

	_, err := New(srv.URL).WithCredentials(store, creds).Me(context.Background())
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Code != "invalid_refresh_token" {
		t.Fatalf("err = %v", err)
	}
	if _, err := store.Load(srv.URL); !errors.Is(err, config.ErrNotLoggedIn) {
		t.Fatalf("credentials not cleared: %v", err)
	}
}

func TestDotenvErrorsAreDecoded(t *testing.T) {
	var calls int32
	srv := fakeServer(t, &calls)
	c := New(srv.URL).WithToken("ci-token")
	_, err := c.Import(context.Background(), EnvRef{"p", "e"}, "A=1\n1A=2", nil, true)
	errs := DotenvErrors(err)
	if len(errs) != 1 || errs[0].Line != 2 || errs[0].Code != "invalid_key" {
		t.Fatalf("errs = %+v (err %v)", errs, err)
	}
	if err.Error() != "the .env file has errors" {
		t.Errorf("message = %q", err.Error())
	}
}
