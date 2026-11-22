// Package commands implements the envo subcommands.
package commands

import (
	"fmt"
	"io"
)

// Version is overridden at build time: -ldflags "-X envo/cli/internal/commands.Version=..."
var Version = "dev"

type command struct {
	name    string
	summary string
}

// The MVP command set (see MVP_PLAN.md, "CLI sözleşmesi"). They are wired to
// the API in phase 3.
var planned = []command{
	{"login", "Sign in through the browser"},
	{"init", "Link this directory to an Envo project (writes envo.yaml)"},
	{"pull", "Write an environment's variables to .env"},
	{"push", "Merge a local .env into an environment"},
	{"set", "Set a single variable"},
	{"run", "Run a command with an environment's variables, without writing .env"},
}

// Run executes the CLI and returns the process exit code.
func Run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		usage(stdout)
		return 0
	}
	switch args[0] {
	case "-h", "--help", "help":
		usage(stdout)
		return 0
	case "-v", "--version", "version":
		fmt.Fprintf(stdout, "envo %s\n", Version)
		return 0
	}
	for _, c := range planned {
		if c.name == args[0] {
			fmt.Fprintf(stderr, "envo %s: not implemented yet\n", c.name)
			return 1
		}
	}
	fmt.Fprintf(stderr, "envo: unknown command %q\n\n", args[0])
	usage(stderr)
	return 2
}

func usage(w io.Writer) {
	fmt.Fprintln(w, "Envo: one place for every environment.")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Usage:")
	fmt.Fprintln(w, "  envo <command> [flags]")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Commands:")
	for _, c := range planned {
		fmt.Fprintf(w, "  %-8s %s\n", c.name, c.summary)
	}
	fmt.Fprintf(w, "  %-8s %s\n", "version", "Print the CLI version")
}
