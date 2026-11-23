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
	fs := newFlags(a, "pull", "pull [--env SLUG] [--path FOLDER | --all] [--output PATH|-] [--force]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	var folder folderFlag
	addFolderFlag(fs, &folder)
	all := fs.Bool("all", false, "write every folder's .env into its directory\n(default at the project root)")
	output := fs.String("output", "", "file to write, or - for stdout (default: the folder's .env)")
	force := fs.Bool("force", false, "overwrite existing files without asking")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}
	if *all && (folder.set || *output != "") {
		return usagef("--all writes each folder's own .env; it cannot be combined with --path or --output")
	}

	t, err := a.resolveEnvironment(ctx, *envSlug)
	if err != nil {
		return err
	}
	// At the project root, a plain pull writes every folder's .env.
	if *all || (!folder.set && *output == "" && t.atRoot()) {
		return pullAll(ctx, a, t, *force)
	}
	if err := t.resolveFolder(ctx, &folder); err != nil {
		return err
	}
	file := *output
	if file == "" {
		file = t.localFile(t.ref.Folder)
	}
	if file != "-" {
		if err := confirmOverwrite(a, []string{file}, *force); err != nil {
			return err
		}
	}

	data, err := t.client.ExportDotenv(ctx, t.ref)
	if err != nil {
		return err
	}
	if file == "-" {
		_, err := a.io.Out.Write(data)
		return err
	}
	if err := writePrivateFile(file, data); err != nil {
		return err
	}
	a.io.printf("Wrote %d variable(s) from %s to %s.\n", countLines(data), t.label(), display(file))
	return nil
}

// pullAll writes each folder's .env of the environment into the matching
// directory. Folders with no variables, or whose directory does not exist in
// this checkout (the code may be at another revision), are skipped.
func pullAll(ctx context.Context, a *app, t *target, force bool) error {
	folders, err := t.folders(ctx)
	if err != nil {
		return err
	}
	type file struct {
		folder, path string
		data         []byte
	}
	var files []file
	for _, f := range folders {
		ref := t.ref
		ref.Folder = f
		data, err := t.client.ExportDotenv(ctx, ref)
		if err != nil {
			return err
		}
		if len(data) == 0 {
			continue
		}
		path := t.localFile(f)
		if info, err := os.Stat(filepath.Dir(path)); err != nil || !info.IsDir() {
			a.io.printf("Skipped %s/.env: directory %s does not exist.\n", f, display(filepath.Dir(path)))
			continue
		}
		files = append(files, file{f, path, data})
	}
	if len(files) == 0 {
		a.io.printf("Nothing to write: %s has no variables in any folder present here.\n", t.env.Slug)
		return nil
	}

	paths := make([]string, len(files))
	for i, f := range files {
		paths[i] = f.path
	}
	if err := confirmOverwrite(a, paths, force); err != nil {
		return err
	}
	for _, f := range files {
		if err := writePrivateFile(f.path, f.data); err != nil {
			return err
		}
		a.io.printf("Wrote %d variable(s) to %s.\n", countLines(f.data), display(f.path))
	}
	return nil
}

// confirmOverwrite asks once before replacing existing files.
func confirmOverwrite(a *app, paths []string, force bool) error {
	var existing []string
	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			existing = append(existing, display(p))
		}
	}
	if len(existing) == 0 || force {
		return nil
	}
	what := existing[0] + " already exists"
	if len(existing) > 1 {
		what = fmt.Sprintf("%d files already exist (%s, ...)", len(existing), existing[0])
	}
	if !a.io.IsTerm {
		return fmt.Errorf("%s; use --force to overwrite", what)
	}
	ok, err := a.io.confirm(what+". Overwrite?", false)
	if err != nil {
		return err
	}
	if !ok {
		return errAborted
	}
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
	fs := newFlags(a, "push",
		"push [--env SLUG] [--path FOLDER] [--file PATH] [--visible KEY]... [--replace] [--dry-run] [--yes]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	var folder folderFlag
	addFolderFlag(fs, &folder)
	file := fs.String("file", "", "file to read (default: the folder's .env)")
	var visible listFlag
	fs.Var(&visible, "visible", "create KEY as visible instead of secret (repeatable, comma-separated)")
	replace := fs.Bool("replace", false, "delete keys that are not in the file")
	dryRun := fs.Bool("dry-run", false, "show what would change without writing")
	yes := fs.Bool("yes", false, "do not ask for confirmation")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}

	t, err := a.resolveTarget(ctx, *envSlug, &folder)
	if err != nil {
		return err
	}
	path := *file
	if path == "" {
		path = t.localFile(t.ref.Folder)
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	name := display(path)
	visibility := map[string]string{}
	for _, k := range visible {
		visibility[k] = "visible"
	}

	preview, err := t.client.Import(ctx, t.ref, string(content), visibility, true, *replace)
	if err != nil {
		return describeImportError(a, name, err)
	}
	changes := printPreview(a, preview)
	if changes == 0 {
		a.io.printf("Nothing to push: %s already matches %s.\n", t.label(), name)
		return nil
	}
	if *dryRun {
		return nil
	}
	if a.io.IsTerm && !*yes {
		ok, err := a.io.confirm(fmt.Sprintf("Push %d change(s) to %s?", changes, t.label()), false)
		if err != nil {
			return err
		}
		if !ok {
			return errAborted
		}
	}
	result, err := t.client.Import(ctx, t.ref, string(content), visibility, false, *replace)
	if err != nil {
		return describeImportError(a, name, err)
	}
	if *replace {
		a.io.printf("Pushed to %s (revision %d). Keys not in %s were deleted.\n",
			t.label(), result.Revision, name)
	} else {
		a.io.printf("Pushed to %s (revision %d). Keys not in %s were left unchanged.\n",
			t.label(), result.Revision, name)
	}
	return nil
}

func printPreview(a *app, r *api.ImportResult) int {
	marks := map[string]string{"new": "+", "changed": "~", "unchanged": "=", "deleted": "-"}
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
	fs := newFlags(a, "set", "set KEY [--env SLUG] [--path FOLDER] [--visible]\n\n"+
		"The value is read from a hidden prompt, or from stdin when piped.")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	var folder folderFlag
	addFolderFlag(fs, &folder)
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

	t, err := a.resolveTarget(ctx, *envSlug, &folder)
	if err != nil {
		return err
	}
	value, err := a.io.readSecret(fmt.Sprintf("Value for %s (%s): ", key, t.label()))
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
		a.io.printf("Created %s in %s (revision %d).\n", key, t.label(), result.Revision)
	case len(result.Updated) > 0:
		a.io.printf("Updated %s in %s (revision %d).\n", key, t.label(), result.Revision)
	default:
		a.io.printf("%s in %s is unchanged.\n", key, t.label())
	}
	return nil
}

func runRun(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "run", "run [--env SLUG] [--path FOLDER] -- COMMAND [ARGS...]")
	envSlug := fs.String("env", "", "environment slug (default: from envo.yaml)")
	var folder folderFlag
	addFolderFlag(fs, &folder)
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
		return usagef("missing command; usage: envo run [--env SLUG] [--path FOLDER] -- COMMAND [ARGS...]")
	}

	t, err := a.resolveTarget(ctx, *envSlug, &folder)
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
	a.io.printf("envo: injecting %d variable(s) from %s\n", len(keys), t.label())

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
