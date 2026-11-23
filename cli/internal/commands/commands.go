// Package commands implements the envo subcommands.
package commands

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"

	"envo/cli/internal/api"
	"envo/cli/internal/config"
)

// Version is overridden at build time: -ldflags "-X envo/cli/internal/commands.Version=..."
var Version = "dev"

type command struct {
	name    string
	summary string
	run     func(ctx context.Context, a *app, args []string) error
}

var commandList []command

func init() {
	commandList = []command{
		{"login", "Sign in through the browser", runLogin},
		{"logout", "Sign out on this machine", runLogout},
		{"whoami", "Show the signed-in user and server", runWhoami},
		{"init", "Link this directory to an Envo project (writes envo.yaml)", runInit},
		{"pull", "Write an environment's variables to .env (one folder or --all)", runPull},
		{"push", "Merge (or --replace) a local .env into an environment", runPush},
		{"set", "Set a single variable (value from a hidden prompt or stdin)", runSet},
		{"run", "Run a command with an environment's variables, without writing .env", runRun},
	}
}

// exitError carries a specific process exit code (used by `run`).
type exitError struct{ code int }

func (e *exitError) Error() string { return fmt.Sprintf("exit status %d", e.code) }

// usageError makes the CLI print a hint and exit with code 2.
type usageError struct{ msg string }

func (e *usageError) Error() string { return e.msg }

func usagef(format string, args ...any) error {
	return &usageError{fmt.Sprintf(format, args...)}
}

// app carries the I/O streams and lazily created dependencies.
type app struct {
	io    *IO
	store config.CredentialStore
}

// Run executes the CLI and returns the process exit code.
func Run(args []string, stdout, stderr io.Writer) int {
	streams := stdIO()
	streams.Out, streams.Err = stdout, stderr
	return runWith(args, streams)
}

func runWith(args []string, streams *IO) int {
	if len(args) == 0 {
		usage(streams.Out)
		return 0
	}
	switch args[0] {
	case "-h", "--help", "help":
		usage(streams.Out)
		return 0
	case "-v", "--version", "version":
		fmt.Fprintf(streams.Out, "envo %s\n", Version)
		return 0
	}
	var cmd *command
	for i := range commandList {
		if commandList[i].name == args[0] {
			cmd = &commandList[i]
		}
	}
	if cmd == nil {
		fmt.Fprintf(streams.Err, "envo: unknown command %q\n\n", args[0])
		usage(streams.Err)
		return 2
	}

	ctx, stop := context.WithCancel(context.Background())
	defer stop()
	if cmd.name != "run" {
		// `run` forwards signals to its child itself.
		ctx, stop = signal.NotifyContext(ctx, os.Interrupt)
		defer stop()
	}

	err := cmd.run(ctx, &app{io: streams}, args[1:])
	var exit *exitError
	var usageErr *usageError
	switch {
	case err == nil:
		return 0
	case errors.As(err, &exit):
		return exit.code
	case errors.Is(err, flag.ErrHelp):
		return 0
	case errors.As(err, &usageErr):
		fmt.Fprintf(streams.Err, "envo %s: %s\nRun `envo %s -h` for usage.\n", cmd.name, err, cmd.name)
		return 2
	case errors.Is(err, errAborted):
		fmt.Fprintln(streams.Err, "Aborted.")
		return 1
	default:
		fmt.Fprintf(streams.Err, "envo %s: %s\n", cmd.name, err)
		return 1
	}
}

func usage(w io.Writer) {
	fmt.Fprintln(w, "Envo: one place for every environment.")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Usage:")
	fmt.Fprintln(w, "  envo <command> [flags]")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Commands:")
	for _, c := range commandList {
		fmt.Fprintf(w, "  %-8s %s\n", c.name, c.summary)
	}
	fmt.Fprintf(w, "  %-8s %s\n", "version", "Print the CLI version")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "Environment:")
	fmt.Fprintln(w, "  ENVO_API_URL            Envo server URL (default from envo.yaml or login)")
	fmt.Fprintln(w, "  ENVO_TOKEN              Bearer token for CI; skips stored credentials")
	fmt.Fprintln(w, "  ENVO_CREDENTIALS_STORE  keychain (default, with file fallback) or file")
}

// newFlags creates a flag set that reports errors instead of exiting.
func newFlags(a *app, name, synopsis string) *flag.FlagSet {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(a.io.Err)
	fs.Usage = func() {
		fmt.Fprintf(a.io.Err, "Usage: envo %s\n\nFlags:\n", synopsis)
		fs.PrintDefaults()
	}
	return fs
}

// parseInterspersed parses flags that may appear before or after positional
// arguments. Everything after "--" is returned as-is in rest.
func parseInterspersed(fs *flag.FlagSet, args []string) (positional, rest []string, err error) {
	for i, a := range args {
		if a == "--" {
			rest = args[i+1:]
			args = args[:i]
			break
		}
	}
	for {
		if err := parseFlags(fs, args); err != nil {
			return nil, nil, err
		}
		args = fs.Args()
		if len(args) == 0 {
			return positional, rest, nil
		}
		positional = append(positional, args[0])
		args = args[1:]
	}
}

// parseFlags parses flags; on a bad flag the flag package has already printed
// the problem and the usage, so only the exit code (2) is left to report.
func parseFlags(fs *flag.FlagSet, args []string) error {
	err := fs.Parse(args)
	if err != nil && !errors.Is(err, flag.ErrHelp) {
		return &exitError{code: 2}
	}
	return err
}

// listFlag collects a repeatable (and comma-separated) string flag.
type listFlag []string

func (l *listFlag) String() string { return strings.Join(*l, ",") }

func (l *listFlag) Set(v string) error {
	for _, part := range strings.Split(v, ",") {
		if part = strings.TrimSpace(part); part != "" {
			*l = append(*l, part)
		}
	}
	return nil
}

// --- Shared plumbing -----------------------------------------------------------

func (a *app) credentialStore() (config.CredentialStore, error) {
	if a.store == nil {
		store, err := config.NewCredentialStore()
		if err != nil {
			return nil, err
		}
		a.store = store
	}
	return a.store, nil
}

// client returns an authenticated client for the resolved server URL.
func (a *app) client(project *config.Project) (*api.Client, error) {
	user, err := config.LoadUser()
	if err != nil {
		return nil, err
	}
	apiURL := config.ResolveAPIURL("", project, user)
	c := api.New(apiURL)
	if token := os.Getenv("ENVO_TOKEN"); token != "" {
		return c.WithToken(token), nil
	}
	store, err := a.credentialStore()
	if err != nil {
		return nil, err
	}
	creds, err := store.Load(apiURL)
	if err != nil {
		if errors.Is(err, config.ErrNotLoggedIn) {
			return nil, fmt.Errorf("not logged in to %s; run `envo login`", apiURL)
		}
		return nil, err
	}
	return c.WithCredentials(store, creds), nil
}

// target is a resolved project environment.
type target struct {
	project *config.Project
	env     api.Environment
	ref     api.EnvRef
	client  *api.Client
}

// resolveTarget loads envo.yaml, finds the environment by slug and picks the
// folder from --path or the working directory.
func (a *app) resolveTarget(ctx context.Context, envSlug string, folder *folderFlag) (*target, error) {
	t, err := a.resolveEnvironment(ctx, envSlug)
	if err != nil {
		return nil, err
	}
	if err := t.resolveFolder(ctx, folder); err != nil {
		return nil, err
	}
	return t, nil
}

// resolveEnvironment loads envo.yaml and finds the environment by slug.
func (a *app) resolveEnvironment(ctx context.Context, envSlug string) (*target, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return nil, err
	}
	project, err := config.FindProject(cwd)
	if err != nil {
		return nil, err
	}
	client, err := a.client(project)
	if err != nil {
		return nil, err
	}
	if envSlug == "" {
		envSlug = project.DefaultEnvironment
	}
	envs, err := client.Environments(ctx, project.ProjectID)
	if err != nil {
		return nil, err
	}
	for _, e := range envs {
		if e.Slug == envSlug {
			return &target{
				project: project,
				env:     e,
				ref:     api.EnvRef{ProjectID: project.ProjectID, EnvID: e.ID},
				client:  client,
			}, nil
		}
	}
	slugs := make([]string, 0, len(envs))
	for _, e := range envs {
		slugs = append(slugs, e.Slug)
	}
	return nil, fmt.Errorf("environment %q not found in %s (available: %s)",
		envSlug, project.Project, strings.Join(slugs, ", "))
}
