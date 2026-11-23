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

func TestCleanFolder(t *testing.T) {
	for in, want := range map[string]string{
		"": "", ".": "", "/": "", " backend/ ": "backend", `services\api`: "services/api", "./a//b/.": "a/b",
	} {
		if got, err := cleanFolder(in); err != nil || got != want {
			t.Errorf("cleanFolder(%q) = %q, %v; want %q", in, got, err, want)
		}
	}
	if _, err := cleanFolder("a/../b"); err == nil {
		t.Error("expected an error for ..")
	}
}

func TestPickFolder(t *testing.T) {
	folders := []string{"", "backend", "backend/worker", "back"}
	for rel, want := range map[string]string{
		"":                   "",
		"backend":            "backend",
		"backend/src/models": "backend",
		"backend/worker/x":   "backend/worker",
		"backends":           "",
		"docs":               "",
	} {
		if got := pickFolder(folders, rel); got != want {
			t.Errorf("pickFolder(%q) = %q; want %q", rel, got, want)
		}
	}
}

func TestRelativeFolder(t *testing.T) {
	root := filepath.Join(t.TempDir(), "repo")
	for dir, want := range map[string]string{
		root:                                  "",
		filepath.Join(root, "backend", "src"): "backend/src",
		filepath.Dir(root):                    "",
	} {
		if got := relativeFolder(root, dir); got != want {
			t.Errorf("relativeFolder(%q) = %q; want %q", dir, got, want)
		}
	}
}

// fakeEnvo serves one project ("p") with a development environment whose
// folders hold one variable each, and records the requested export paths.
func fakeEnvo(t *testing.T, requested *[]string) *httptest.Server {
	t.Helper()
	values := map[string]string{"": "ROOT=1\n", "backend": "DB=dev\n", "backend/worker": "Q=jobs\n", "gone": "OLD=1\n"}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/projects/p/environments", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`[{"id":"e","name":"Development","slug":"development"}]`))
	})
	mux.HandleFunc("GET /api/projects/p/folders", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"folders":    []string{"", "backend", "backend/worker", "frontend", "gone", "services"},
			"env_files":  []string{"", "backend", "backend/worker", "gone"},
			"can_manage": false,
		})
	})
	mux.HandleFunc("GET /api/projects/p/environments/e/export", func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Query().Get("path")
		*requested = append(*requested, path)
		if r.URL.Query().Get("format") == "json" {
			key, value, _ := strings.Cut(strings.TrimSpace(values[path]), "=")
			_ = json.NewEncoder(w).Encode(map[string]string{key: value})
			return
		}
		_, _ = w.Write([]byte(values[path]))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

// repo creates a linked checkout with backend/src and frontend directories.
func repo(t *testing.T, apiURL string) string {
	t.Helper()
	root := t.TempDir()
	for _, d := range []string{"backend/src", "backend/worker", "frontend"} {
		if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(d)), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	link := "api_url: " + apiURL + "\nproject: acme/shop\nproject_id: p\ndefault_environment: development\n"
	if err := os.WriteFile(filepath.Join(root, "envo.yaml"), []byte(link), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("ENVO_CONFIG_DIR", t.TempDir())
	t.Setenv("ENVO_TOKEN", "envo_st_test")
	t.Setenv("ENVO_API_URL", "")
	return root
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		return "<missing>"
	}
	return string(data)
}

func TestPullUsesTheFolderOfTheWorkingDirectory(t *testing.T) {
	var requested []string
	root := repo(t, fakeEnvo(t, &requested).URL)

	// Inside backend/src: the deepest project folder is backend, and its
	// .env lands in backend/, not in the working directory.
	t.Chdir(filepath.Join(root, "backend", "src"))
	code, out, errOut := run(t, "", "pull")
	if code != 0 {
		t.Fatalf("code %d, stdout %q, stderr %q", code, out, errOut)
	}
	if got := readFile(t, filepath.Join(root, "backend", ".env")); got != "DB=dev\n" {
		t.Fatalf("backend/.env = %q", got)
	}
	if !strings.Contains(errOut, "development (backend/.env)") {
		t.Fatalf("stderr %q", errOut)
	}

	// --path overrides detection; "/" is the root.
	code, out, _ = run(t, "", "pull", "--path", "/", "--output", "-")
	if code != 0 || out != "ROOT=1\n" {
		t.Fatalf("code %d, stdout %q", code, out)
	}
	if strings.Join(requested, ",") != "backend," {
		t.Fatalf("requested %q", requested)
	}
}

func TestPullAllWritesEveryFolderPresentInTheCheckout(t *testing.T) {
	var requested []string
	root := repo(t, fakeEnvo(t, &requested).URL)
	t.Chdir(root)
	_ = os.WriteFile(filepath.Join(root, ".env"), []byte("STALE=1\n"), 0o600)

	// Not a terminal: existing files need --force.
	code, _, errOut := run(t, "", "pull", "--all")
	if code != 1 || !strings.Contains(errOut, "--force") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
	code, out, errOut := run(t, "", "pull", "--all", "--force")
	if code != 0 {
		t.Fatalf("code %d, stdout %q, stderr %q", code, out, errOut)
	}
	for path, want := range map[string]string{
		".env":                "ROOT=1\n",
		"backend/.env":        "DB=dev\n",
		"backend/worker/.env": "Q=jobs\n",
		"frontend/.env":       "<missing>", // no variables in this environment
	} {
		if got := readFile(t, filepath.Join(root, filepath.FromSlash(path))); got != want {
			t.Errorf("%s = %q; want %q", path, got, want)
		}
	}
	// The folder's directory does not exist in this checkout.
	if !strings.Contains(errOut, "Skipped gone/.env") {
		t.Fatalf("stderr %q", errOut)
	}
	if code, _, _ := run(t, "", "pull", "--all", "--path", "backend"); code != 2 {
		t.Fatalf("--all with --path: code %d", code)
	}
}

func TestRunInjectsTheFolderEnv(t *testing.T) {
	var requested []string
	root := repo(t, fakeEnvo(t, &requested).URL)
	t.Chdir(filepath.Join(root, "backend", "worker"))
	code, _, errOut := run(t, "", "run", "--", "go", "version")
	if code != 0 {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
	if strings.Join(requested, ",") != "backend/worker" {
		t.Fatalf("requested %q", requested)
	}
}
