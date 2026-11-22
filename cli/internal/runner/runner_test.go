package runner

import (
	"bytes"
	"fmt"
	"os"
	"strconv"
	"strings"
	"testing"
)

func TestMergeEnvOverridesAndKeepsOthers(t *testing.T) {
	base := []string{"PATH=/bin", "HOME=/home/u", "API_KEY=old", "=C:=C:\\dir"}
	got := mergeEnv(base, map[string]string{"API_KEY": "new", "DB": "x=y"}, false)
	want := []string{"PATH=/bin", "HOME=/home/u", "=C:=C:\\dir", "API_KEY=new", "DB=x=y"}
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Fatalf("got %v, want %v", got, want)
	}
}

func TestMergeEnvCaseInsensitiveOnWindows(t *testing.T) {
	got := mergeEnv([]string{"Path=C:\\bin", "api_key=old"}, map[string]string{"API_KEY": "new"}, true)
	want := []string{"Path=C:\\bin", "API_KEY=new"}
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Fatalf("got %v, want %v", got, want)
	}
}

// TestHelperProcess is not a real test: Run re-executes the test binary with
// ENVO_HELPER set to act as a child process.
func TestHelperProcess(t *testing.T) {
	mode := os.Getenv("ENVO_HELPER")
	if mode == "" {
		return
	}
	switch mode {
	case "print-env":
		fmt.Print(os.Getenv("ENVO_TEST_VALUE"))
		os.Exit(0)
	case "exit":
		code, _ := strconv.Atoi(os.Getenv("ENVO_EXIT_CODE"))
		os.Exit(code)
	}
	os.Exit(99)
}

func helper(t *testing.T, mode string, extra map[string]string) (int, string) {
	t.Helper()
	vars := map[string]string{"ENVO_HELPER": mode}
	for k, v := range extra {
		vars[k] = v
	}
	var out, errOut bytes.Buffer
	code, err := Run(os.Args[0], []string{"-test.run=TestHelperProcess"},
		MergeEnv(os.Environ(), vars), nil, &out, &errOut)
	if err != nil {
		t.Fatalf("Run: %v (stderr %q)", err, errOut.String())
	}
	return code, out.String()
}

func TestRunInjectsVariables(t *testing.T) {
	value := "multi\nline value with = and 'quotes' ✓"
	code, out := helper(t, "print-env", map[string]string{"ENVO_TEST_VALUE": value})
	if code != 0 || out != value {
		t.Fatalf("code %d, output %q", code, out)
	}
}

func TestRunPropagatesExitCode(t *testing.T) {
	for _, want := range []int{0, 1, 3, 42} {
		code, _ := helper(t, "exit", map[string]string{"ENVO_EXIT_CODE": strconv.Itoa(want)})
		if code != want {
			t.Errorf("exit code %d, want %d", code, want)
		}
	}
}

func TestRunMissingCommand(t *testing.T) {
	code, err := Run("envo-definitely-missing-command", nil, os.Environ(), nil, nil, nil)
	if code != ExitNotFound || err == nil {
		t.Fatalf("code %d, err %v", code, err)
	}
}
