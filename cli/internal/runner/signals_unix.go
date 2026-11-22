//go:build !windows

package runner

import (
	"os"
	"os/exec"
	"syscall"
)

var forwardedSignals = []os.Signal{syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP, syscall.SIGQUIT}

// forward passes the signal on; envo keeps running until the child exits.
func forward(p *os.Process, sig os.Signal) {
	_ = p.Signal(sig)
}

// exitCode follows shell conventions: 128+N when the child died from signal N.
func exitCode(err *exec.ExitError) int {
	if status, ok := err.Sys().(syscall.WaitStatus); ok && status.Signaled() {
		return 128 + int(status.Signal())
	}
	return err.ExitCode()
}
