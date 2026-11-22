package config

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestProjectRoundTripAndLookupFromSubdirectory(t *testing.T) {
	root := t.TempDir()
	want := &Project{
		APIURL:             "https://envo.example.com",
		Project:            "acme/backend/web-api",
		ProjectID:          "22222222-2222-2222-2222-222222222222",
		DefaultEnvironment: "staging",
	}
	path, err := SaveProject(root, want)
	if err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(path)
	if !strings.HasPrefix(string(data), "# Envo project link") {
		t.Errorf("missing header comment:\n%s", data)
	}

	sub := filepath.Join(root, "services", "api")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	got, err := FindProject(sub)
	if err != nil {
		t.Fatal(err)
	}
	if got.ProjectID != want.ProjectID || got.DefaultEnvironment != "staging" || got.Path != path {
		t.Errorf("got %+v", got)
	}
}

func TestFindProjectMissing(t *testing.T) {
	if _, err := FindProject(t.TempDir()); !errors.Is(err, ErrNoProject) {
		t.Fatalf("err = %v", err)
	}
}

func TestLoadProjectValidates(t *testing.T) {
	path := filepath.Join(t.TempDir(), ProjectFile)
	_ = os.WriteFile(path, []byte("project: acme/web\n"), 0o644)
	if _, err := LoadProject(path); err == nil {
		t.Fatal("expected an error for a file without project_id")
	}
	_ = os.WriteFile(path, []byte("project_id: b\n"), 0o644)
	p, err := LoadProject(path)
	if err != nil || p.DefaultEnvironment != "development" {
		t.Fatalf("p = %+v, err = %v", p, err)
	}
}

func TestResolveAPIURLPrecedence(t *testing.T) {
	t.Setenv("ENVO_API_URL", "")
	p := &Project{APIURL: "https://project.example/"}
	u := &User{APIURL: "https://user.example"}
	if got := ResolveAPIURL("", p, u); got != "https://project.example" {
		t.Errorf("project: %s", got)
	}
	if got := ResolveAPIURL("", nil, u); got != "https://user.example" {
		t.Errorf("user: %s", got)
	}
	if got := ResolveAPIURL("https://flag.example", p, u); got != "https://flag.example" {
		t.Errorf("flag: %s", got)
	}
	t.Setenv("ENVO_API_URL", "https://env.example")
	if got := ResolveAPIURL("", p, u); got != "https://env.example" {
		t.Errorf("env: %s", got)
	}
	t.Setenv("ENVO_API_URL", "")
	if got := ResolveAPIURL("", nil, nil); got != DefaultAPIURL {
		t.Errorf("default: %s", got)
	}
}

func TestFileStore(t *testing.T) {
	store := FileStore{Path: filepath.Join(t.TempDir(), "credentials.json")}
	if _, err := store.Load("https://a"); !errors.Is(err, ErrNotLoggedIn) {
		t.Fatalf("err = %v", err)
	}
	creds := &Credentials{AccessToken: "at", RefreshToken: "rt", AccessExpiresAt: time.Now().Round(0)}
	if err := store.Save("https://a", creds); err != nil {
		t.Fatal(err)
	}
	_ = store.Save("https://b", &Credentials{AccessToken: "other"})
	got, err := store.Load("https://a")
	if err != nil || got.RefreshToken != "rt" {
		t.Fatalf("got %+v, err %v", got, err)
	}
	if runtime.GOOS != "windows" {
		info, _ := os.Stat(store.Path)
		if info.Mode().Perm() != 0o600 {
			t.Errorf("mode %v, want 0600", info.Mode().Perm())
		}
	}
	if err := store.Delete("https://a"); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Load("https://a"); !errors.Is(err, ErrNotLoggedIn) {
		t.Fatalf("after delete: %v", err)
	}
	if got, _ := store.Load("https://b"); got == nil || got.AccessToken != "other" {
		t.Fatalf("other server's credentials lost: %+v", got)
	}
}
