package commands

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// fakeEnvoFiles serves project "p" with a root .env and config files, and
// keeps the config files' contents (by "folder/name") so pushes can be seen.
func fakeEnvoFiles(t *testing.T, contents map[string]string) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/projects/p/environments", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`[{"id":"e","name":"Development","slug":"development"}]`))
	})
	mux.HandleFunc("GET /api/projects/p/folders", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"folders":   []string{"", "backend", "gone"},
			"env_files": []string{""},
			"files": []map[string]string{
				{"path": "", "name": ".env"},
				{"path": "", "name": "empty.json"},
				{"path": "backend", "name": "application.properties"},
				{"path": "gone", "name": "config.yaml"},
			},
		})
	})
	mux.HandleFunc("GET /api/projects/p/environments/e/export", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ROOT=1\n"))
	})
	key := func(r *http.Request) string {
		folder := r.URL.Query().Get("path")
		if folder == "" {
			return r.PathValue("name")
		}
		return folder + "/" + r.PathValue("name")
	}
	mux.HandleFunc("GET /api/projects/p/environments/e/files/{name}", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(contents[key(r)]))
	})
	mux.HandleFunc("PUT /api/projects/p/environments/e/files/{name}", func(w http.ResponseWriter, r *http.Request) {
		var body struct{ Content string }
		_ = json.NewDecoder(r.Body).Decode(&body)
		contents[key(r)] = body.Content
		_, _ = w.Write([]byte(`{"revision":7,"created":[],"updated":[],"deleted":[]}`))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

func TestPullAtTheRootWritesConfigFiles(t *testing.T) {
	contents := map[string]string{
		"backend/application.properties": "server.port=8080\n",
		"gone/config.yaml":               "a: 1\n",
	}
	root := repo(t, fakeEnvoFiles(t, contents).URL)
	t.Chdir(root)
	code, out, errOut := run(t, "", "pull")
	if code != 0 {
		t.Fatalf("code %d, stdout %q, stderr %q", code, out, errOut)
	}
	for path, want := range map[string]string{
		".env":                           "ROOT=1\n",
		"backend/application.properties": "server.port=8080\n",
		"empty.json":                     "<missing>", // empty in this environment
	} {
		if got := readFile(t, filepath.Join(root, filepath.FromSlash(path))); got != want {
			t.Errorf("%s = %q; want %q", path, got, want)
		}
	}
	if !strings.Contains(errOut, "Skipped gone/config.yaml") {
		t.Fatalf("stderr %q", errOut)
	}
}

func TestPullAndPushOneConfigFile(t *testing.T) {
	contents := map[string]string{"backend/application.properties": "server.port=8080\n"}
	root := repo(t, fakeEnvoFiles(t, contents).URL)

	// The FILE argument is relative to the working directory.
	t.Chdir(filepath.Join(root, "backend"))
	code, out, errOut := run(t, "", "pull", "application.properties")
	if code != 0 {
		t.Fatalf("code %d, stdout %q, stderr %q", code, out, errOut)
	}
	local := filepath.Join(root, "backend", "application.properties")
	if got := readFile(t, local); got != "server.port=8080\n" {
		t.Fatalf("application.properties = %q", got)
	}

	// Unchanged: nothing to push.
	code, _, errOut = run(t, "", "push", "application.properties")
	if code != 0 || !strings.Contains(errOut, "Nothing to push") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}

	// Changed: --dry-run shows it, a push replaces it.
	_ = os.WriteFile(local, []byte("server.port=9090\n"), 0o600)
	code, _, errOut = run(t, "", "push", "application.properties", "--dry-run")
	if code != 0 || !strings.Contains(errOut, "~ backend/application.properties") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
	if contents["backend/application.properties"] != "server.port=8080\n" {
		t.Fatal("--dry-run wrote")
	}
	code, _, errOut = run(t, "", "push", "application.properties")
	if code != 0 || !strings.Contains(errOut, "revision 7") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
	if contents["backend/application.properties"] != "server.port=9090\n" {
		t.Fatalf("pushed %q", contents["backend/application.properties"])
	}

	// A new file at the root, from a subdirectory.
	_ = os.WriteFile(filepath.Join(root, "settings.json"), []byte("{}"), 0o600)
	if code, _, errOut := run(t, "", "push", "../settings.json"); code != 0 {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
	if contents["settings.json"] != "{}" {
		t.Fatalf("contents %q", contents)
	}

	// .env-only flags do not apply; files outside the project are refused.
	if code, _, _ := run(t, "", "push", "application.properties", "--replace"); code != 2 {
		t.Fatalf("--replace with a config file: code %d", code)
	}
	outside := filepath.Join(t.TempDir(), "x.json")
	if code, _, errOut := run(t, "", "pull", outside); code != 1 || !strings.Contains(errOut, "outside the project") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
}
