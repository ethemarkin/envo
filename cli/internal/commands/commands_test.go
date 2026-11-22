package commands

import (
	"bytes"
	"flag"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func run(t *testing.T, stdin string, args ...string) (int, string, string) {
	t.Helper()
	var out, errOut bytes.Buffer
	code := runWith(args, &IO{In: strings.NewReader(stdin), Out: &out, Err: &errOut})
	return code, out.String(), errOut.String()
}

func TestTopLevel(t *testing.T) {
	cases := []struct {
		args     []string
		code     int
		inStdout string
		inStderr string
	}{
		{nil, 0, "Usage:", ""},
		{[]string{"version"}, 0, "envo dev", ""},
		{[]string{"bogus"}, 2, "", "unknown command"},
		{[]string{"set"}, 2, "", "missing KEY"},
		{[]string{"set", "KEY", "value"}, 2, "", "shell history"},
		{[]string{"run"}, 2, "", "missing command"},
		{[]string{"pull", "--nope"}, 2, "", "flag provided but not defined"},
	}
	for _, tc := range cases {
		code, out, errOut := run(t, "", tc.args...)
		if code != tc.code || !strings.Contains(out, tc.inStdout) || !strings.Contains(errOut, tc.inStderr) {
			t.Errorf("%v: code %d, stdout %q, stderr %q", tc.args, code, out, errOut)
		}
	}
}

func TestCommandsNeedAProjectLink(t *testing.T) {
	t.Chdir(t.TempDir())
	t.Setenv("ENVO_CONFIG_DIR", t.TempDir())
	code, _, errOut := run(t, "", "pull")
	if code != 1 || !strings.Contains(errOut, "envo init") {
		t.Fatalf("code %d, stderr %q", code, errOut)
	}
}

func TestParseInterspersed(t *testing.T) {
	fs := flag.NewFlagSet("t", flag.ContinueOnError)
	env := fs.String("env", "", "")
	visible := fs.Bool("visible", false, "")
	pos, rest, err := parseInterspersed(fs, []string{"KEY", "--env", "prod", "--visible", "--", "x", "--y"})
	if err != nil || *env != "prod" || !*visible {
		t.Fatalf("err %v env %q visible %v", err, *env, *visible)
	}
	if strings.Join(pos, ",") != "KEY" || strings.Join(rest, ",") != "x,--y" {
		t.Fatalf("pos %v rest %v", pos, rest)
	}
}

func TestListFlag(t *testing.T) {
	var l listFlag
	_ = l.Set("A, B")
	_ = l.Set("C")
	if strings.Join(l, ",") != "A,B,C" {
		t.Fatalf("got %v", l)
	}
}

func TestReadSecretFromPipe(t *testing.T) {
	s := &IO{In: strings.NewReader("line one\nline two\r\n")}
	got, err := s.readSecret("")
	if err != nil || got != "line one\nline two" {
		t.Fatalf("got %q, err %v", got, err)
	}
}

func TestPromptsShareBufferedInput(t *testing.T) {
	s := &IO{In: strings.NewReader("x\n2\ny\n"), Err: &bytes.Buffer{}}
	i, err := s.choose("pick", []string{"a", "b"})
	if err != nil || i != 1 {
		t.Fatalf("choose = %d, %v", i, err)
	}
	ok, err := s.confirm("sure?", false)
	if err != nil || !ok {
		t.Fatalf("confirm = %v, %v", ok, err)
	}
}

func TestEnsureGitignored(t *testing.T) {
	dir := t.TempDir()
	a := &app{io: &IO{In: strings.NewReader(""), Err: &bytes.Buffer{}}}
	path := filepath.Join(dir, ".gitignore")
	_ = os.WriteFile(path, []byte("node_modules"), 0o644)

	if err := ensureGitignored(a, dir, true); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(path)
	if string(data) != "node_modules\n# Local environment (envo pull)\n.env\n" {
		t.Fatalf("gitignore = %q", data)
	}
	// Already covered: no second entry.
	_ = ensureGitignored(a, dir, true)
	again, _ := os.ReadFile(path)
	if string(again) != string(data) {
		t.Fatalf("entry added twice: %q", again)
	}
}
