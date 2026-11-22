// Package runner starts a child process with injected environment variables,
// forwards termination signals to it and reports its exit code. Nothing is
// written to disk.
package runner

import (
	"errors"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"runtime"
	"sort"
	"strings"
)

// Exit codes used when the child could not be started (shell conventions).
const (
	ExitCannotExecute = 126
	ExitNotFound      = 127
)

// MergeEnv returns base ("KEY=value" entries) with vars added; vars replace
// existing entries. Windows treats variable names case-insensitively.
func MergeEnv(base []string, vars map[string]string) []string {
	return mergeEnv(base, vars, runtime.GOOS == "windows")
}

func mergeEnv(base []string, vars map[string]string, caseInsensitive bool) []string {
	norm := func(k string) string {
		if caseInsensitive {
			return strings.ToUpper(k)
		}
		return k
	}
	override := make(map[string]bool, len(vars))
	for k := range vars {
		override[norm(k)] = true
	}
	out := make([]string, 0, len(base)+len(vars))
	for _, entry := range base {
		name, _, _ := strings.Cut(entry, "=")
		// Windows has hidden per-drive entries like "=C:=C:\\dir"; keep them.
		if name != "" && override[norm(name)] {
			continue
		}
		out = append(out, entry)
	}
	keys := make([]string, 0, len(vars))
	for k := range vars {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		out = append(out, k+"="+vars[k])
	}
	return out
}

// Run executes name with args and env, wiring the standard streams through,
// and returns the child's exit code.
func Run(name string, args []string, env []string, stdin io.Reader, stdout, stderr io.Writer) (int, error) {
	cmd := exec.Command(name, args...)
	cmd.Env = env
	cmd.Stdin, cmd.Stdout, cmd.Stderr = stdin, stdout, stderr

	// Catch signals before starting so none slips through the gap.
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, forwardedSignals...)
	defer signal.Stop(signals)

	if err := cmd.Start(); err != nil {
		if errors.Is(err, exec.ErrNotFound) || errors.Is(err, os.ErrNotExist) {
			return ExitNotFound, err
		}
		return ExitCannotExecute, err
	}

	done := make(chan struct{})
	go func() {
		for {
			select {
			case sig := <-signals:
				forward(cmd.Process, sig)
			case <-done:
				return
			}
		}
	}()
	err := cmd.Wait()
	close(done)
	if err == nil {
		return 0, nil
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitCode(exitErr), nil
	}
	return 1, err
}
