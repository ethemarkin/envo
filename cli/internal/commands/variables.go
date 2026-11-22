package commands

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"envo/cli/internal/api"
	"envo/cli/internal/runner"
)

func runPull(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "pull", "pull [--env SLUG] [--output PATH|-] [--force]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	output := fs.String("output", ".env", "file to write, or - for stdout")
	force := fs.Bool("force", false, "overwrite an existing file without asking")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}

	t, err := a.resolveTarget(ctx, *envSlug)
	if err != nil {
		return err
	}
	if *output != "-" {
		if _, err := os.Stat(*output); err == nil && !*force {
			if !a.io.IsTerm {
				return fmt.Errorf("%s already exists; use --force to overwrite", *output)
			}
			ok, err := a.io.confirm(fmt.Sprintf("%s already exists. Overwrite?", *output), false)
			if err != nil {
				return err
			}
			if !ok {
				return errAborted
			}
		}
	}

	data, err := t.client.ExportDotenv(ctx, t.ref)
	if err != nil {
		return err
	}
	if *output == "-" {
		_, err := a.io.Out.Write(data)
		return err
	}
	if err := writePrivateFile(*output, data); err != nil {
		return err
	}
	a.io.printf("Wrote %d variable(s) from %s to %s.\n", countLines(data), t.env.Slug, *output)
	return nil
}

// writePrivateFile writes atomically with owner-only permissions.
func writePrivateFile(path string, data []byte) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".envo-pull-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	// CreateTemp already uses 0600 on Unix; on Windows this is best effort.
	_ = tmp.Chmod(0o600)
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), path)
}

// countLines counts KEY= lines in an exported document (values never contain
// raw newlines in exports: multi-line values are quoted and escaped).
func countLines(data []byte) int {
	n := 0
	for _, b := range data {
		if b == '\n' {
			n++
		}
	}
	return n
}

func runPush(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "push", "push [--env SLUG] [--file PATH] [--visible KEY]... [--dry-run] [--yes]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	file := fs.String("file", ".env", "file to read")
	var visible listFlag
	fs.Var(&visible, "visible", "create KEY as visible instead of secret (repeatable, comma-separated)")
	dryRun := fs.Bool("dry-run", false, "show what would change without writing")
	yes := fs.Bool("yes", false, "do not ask for confirmation")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}

	content, err := os.ReadFile(*file)
	if err != nil {
		return err
	}
	t, err := a.resolveTarget(ctx, *envSlug)
	if err != nil {
		return err
	}
	visibility := map[string]string{}
	for _, k := range visible {
		visibility[k] = "visible"
	}

	preview, err := t.client.Import(ctx, t.ref, string(content), visibility, true)
	if err != nil {
		return describeImportError(a, *file, err)
	}
	changes := printPreview(a, preview)
	if changes == 0 {
		a.io.printf("Nothing to push: %s already matches %s.\n", t.env.Slug, *file)
		return nil
	}
	if *dryRun {
		return nil
	}
	if a.io.IsTerm && !*yes {
		ok, err := a.io.confirm(fmt.Sprintf("Push %d change(s) to %s?", changes, t.env.Slug), false)
		if err != nil {
			return err
		}
		if !ok {
			return errAborted
		}
	}
	result, err := t.client.Import(ctx, t.ref, string(content), visibility, false)
	if err != nil {
		return describeImportError(a, *file, err)
	}
	a.io.printf("Pushed to %s (revision %d). Keys not in %s were left unchanged.\n",
		t.env.Slug, result.Revision, *file)
	return nil
}

func printPreview(a *app, r *api.ImportResult) int {
	marks := map[string]string{"new": "+", "changed": "~", "unchanged": "="}
	changes := 0
	for _, item := range r.Items {
		if item.Status != "unchanged" {
			changes++
		}
		a.io.printf("  %s %-32s %s\n", marks[item.Status], item.Key, item.Visibility)
	}
	return changes
}

func describeImportError(a *app, file string, err error) error {
	parseErrors := api.DotenvErrors(err)
	if len(parseErrors) == 0 {
		return err
	}
	for _, e := range parseErrors {
		if e.Line > 0 {
			a.io.printf("  %s:%d: %s\n", file, e.Line, e.Message)
		} else {
			a.io.printf("  %s: %s\n", file, e.Message)
		}
	}
	return fmt.Errorf("%s has errors; nothing was pushed", file)
}

func runSet(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "set", "set KEY [--env SLUG] [--visible]\n\nThe value is read from a hidden prompt, or from stdin when piped.")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	visible := fs.Bool("visible", false, "store as a visible variable (default: secret for new keys)")
	positional, _, err := parseInterspersed(fs, args)
	if err != nil {
		return err
	}
	switch len(positional) {
	case 0:
		return usagef("missing KEY")
	case 1:
	default:
		return usagef("pass the value through the prompt or stdin, not as an argument " +
			"(arguments end up in shell history)")
	}
	key := positional[0]

	t, err := a.resolveTarget(ctx, *envSlug)
	if err != nil {
		return err
	}
	value, err := a.io.readSecret(fmt.Sprintf("Value for %s (%s): ", key, t.env.Slug))
	if err != nil {
		return err
	}
	visibility := ""
	if *visible {
		visibility = "visible"
	}
	result, err := t.client.SetVariable(ctx, t.ref, key, value, visibility)
	if err != nil {
		var apiErr *api.Error
		if errors.As(err, &apiErr) && apiErr.Code == "invalid_key" {
			return fmt.Errorf("invalid key %q: use letters, digits and underscores, not starting with a digit", key)
		}
		return err
	}
	switch {
	case len(result.Created) > 0:
		a.io.printf("Created %s in %s (revision %d).\n", key, t.env.Slug, result.Revision)
	case len(result.Updated) > 0:
		a.io.printf("Updated %s in %s (revision %d).\n", key, t.env.Slug, result.Revision)
	default:
		a.io.printf("%s in %s is unchanged.\n", key, t.env.Slug)
	}
	return nil
}

func runRun(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "run", "run [--env SLUG] -- COMMAND [ARGS...]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	// Flags are only read up to the command: everything from the first
	// non-flag argument (or after "--") belongs to the child process.
	if err := parseFlags(fs, args); err != nil {
		return err
	}
	command := fs.Args()
	if len(command) > 0 && command[0] == "--" {
		command = command[1:]
	}
	if len(command) == 0 {
		return usagef("missing command; usage: envo run [--env SLUG] -- COMMAND [ARGS...]")
	}

	t, err := a.resolveTarget(ctx, *envSlug)
	if err != nil {
		return err
	}
	vars, err := t.client.ExportJSON(ctx, t.ref)
	if err != nil {
		return err
	}
	keys := make([]string, 0, len(vars))
	for k := range vars {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	a.io.printf("envo: injecting %d variable(s) from %s\n", len(keys), t.env.Slug)

	code, err := runner.Run(command[0], command[1:], runner.MergeEnv(os.Environ(), vars),
		a.io.In, a.io.Out, a.io.Err)
	if err != nil {
		a.io.printf("envo run: %s\n", err)
	}
	if code != 0 {
		return &exitError{code: code}
	}
	return nil
}
