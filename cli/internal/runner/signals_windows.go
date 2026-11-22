//go:build windows

package runner

import (
	"os"
	"os/exec"
)

// Ctrl+C / Ctrl+Break reach every process attached to the console, the child
// included. envo only needs to swallow them so it outlives the child and can
// report its exit code.
var forwardedSignals = []os.Signal{os.Interrupt}

func forward(*os.Process, os.Signal) {}

func exitCode(err *exec.ExitError) int {
	return err.ExitCode()
}
