package commands

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"envo/cli/internal/api"
)

// Besides a .env, a folder can hold config files (application.properties,
// config.json, ...) that must not be committed. Their whole text is stored
// per environment. `envo pull` at the project root writes them along with
// the .env files; `envo pull FILE` and `envo push FILE` move a single one.

// files lists every file the project places. Servers without folder support
// have only the root .env.
func (t *target) files(ctx context.Context) ([]api.File, error) {
	files, err := t.client.Files(ctx, t.project.ProjectID)
	var apiErr *api.Error
	if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound && apiErr.Code != "project_not_found" {
		return []api.File{{Folder: "", Name: ".env"}}, nil
	}
	return files, err
}

// configFile is a FILE argument resolved against the project.
type configFile struct {
	folder, name string
	local        string // where it lives in the working copy
}

func (f configFile) label() string {
	if f.folder == "" {
		return f.name
	}
	return f.folder + "/" + f.name
}

// resolveFileArg maps a local path (relative to the working directory) to a
// folder and file name of the project.
func (t *target) resolveFileArg(arg string) (configFile, error) {
	abs, err := filepath.Abs(arg)
	if err != nil {
		return configFile{}, err
	}
	if info, err := os.Stat(abs); err == nil && info.IsDir() {
		return configFile{}, usagef("%s is a directory; pass a file such as %s",
			arg, filepath.Join(arg, "application.properties"))
	}
	rel, err := filepath.Rel(t.projectDir(), abs)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return configFile{}, fmt.Errorf("%s is outside the project (%s)", arg, display(t.projectDir()))
	}
	folder := filepath.ToSlash(filepath.Dir(rel))
	if folder == "." {
		folder = ""
	}
	return configFile{folder: folder, name: filepath.Base(abs), local: abs}, nil
}

// pullFile writes one config file of the environment to output ("" for its
// own place in the working copy, "-" for stdout).
func pullFile(ctx context.Context, a *app, t *target, f configFile, output string, force bool) error {
	ref := t.ref
	ref.Folder = f.folder
	path := f.local
	if output != "" {
		path = output
	}
	if path != "-" {
		if err := confirmOverwrite(a, []string{path}, force); err != nil {
			return err
		}
	}
	data, err := t.client.ReadFile(ctx, ref, f.name)
	if err != nil {
		return describeFileError(f, err)
	}
	if path == "-" {
		_, err := a.io.Out.Write(data)
		return err
	}
	if len(data) == 0 {
		a.io.printf("Note: %s is empty in %s.\n", f.label(), t.env.Slug)
	}
	if err := writePrivateFile(path, data); err != nil {
		return err
	}
	a.io.printf("Wrote %s from %s to %s (%d bytes).\n", f.label(), t.env.Slug, display(path), len(data))
	return nil
}

// pushFile replaces one config file of the environment with a local file.
func pushFile(ctx context.Context, a *app, t *target, f configFile, source string, dryRun, yes bool) error {
	ref := t.ref
	ref.Folder = f.folder
	path := f.local
	if source != "" {
		path = source
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	current, err := t.client.ReadFile(ctx, ref, f.name)
	if err != nil {
		return describeFileError(f, err)
	}
	if bytes.Equal(current, content) {
		a.io.printf("Nothing to push: %s in %s already matches %s.\n", f.label(), t.env.Slug, display(path))
		return nil
	}
	switch {
	case len(current) == 0:
		a.io.printf("  + %s (%d bytes)\n", f.label(), len(content))
	case len(content) == 0:
		a.io.printf("  - %s (cleared)\n", f.label())
	default:
		a.io.printf("  ~ %s (%d -> %d bytes)\n", f.label(), len(current), len(content))
	}
	if dryRun {
		return nil
	}
	if a.io.IsTerm && !yes {
		ok, err := a.io.confirm(fmt.Sprintf("Push %s to %s?", f.label(), t.env.Slug), false)
		if err != nil {
			return err
		}
		if !ok {
			return errAborted
		}
	}
	result, err := t.client.WriteFile(ctx, ref, f.name, content)
	if err != nil {
		return describeFileError(f, err)
	}
	a.io.printf("Pushed %s to %s (revision %d).\n", f.label(), t.env.Slug, result.Revision)
	return nil
}

func describeFileError(f configFile, err error) error {
	var apiErr *api.Error
	if !errors.As(err, &apiErr) {
		return err
	}
	switch apiErr.Code {
	case "invalid_file_name":
		return fmt.Errorf("invalid file name %q: use letters, digits, dots, hyphens and underscores", f.name)
	case "value_too_long":
		return fmt.Errorf("%s is too large (config files can be up to 256 KB)", f.label())
	case "http_404", "not_found":
		return fmt.Errorf("this Envo server does not support config files; upgrade it to use %s", f.label())
	}
	return err
}
