package commands

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"envo/cli/internal/api"
)

// A project's variables live in folders that mirror the repository: "" is
// the project root (next to envo.yaml), "backend" is the backend/ directory,
// and so on. The project decides which of them hold a .env (the same in every
// environment).
//
// Without --path, commands use the deepest .env location that contains the
// working directory, so `envo run` inside backend/src uses backend's .env.
// `envo pull` at the project root writes every folder's .env instead.
// When no location contains it (e.g. the root has no .env), a project with a
// single .env uses that one; with several, --path or --all must choose.

// folderFlag is --path. Unset means "detect from the working directory".
type folderFlag struct {
	value string
	set   bool
}

func (f *folderFlag) String() string { return f.value }

func (f *folderFlag) Set(v string) error {
	p, err := cleanFolder(v)
	if err != nil {
		return err
	}
	f.value, f.set = p, true
	return nil
}

func addFolderFlag(fs *flag.FlagSet, f *folderFlag) {
	fs.Var(f, "path", "project folder whose .env to use, e.g. backend or / for the root\n"+
		"(default: the folder of the current directory)")
}

// cleanFolder normalizes a folder path: forward slashes, no leading or
// trailing slash; "", "." and "/" are the root.
func cleanFolder(raw string) (string, error) {
	parts := []string{}
	for _, s := range strings.Split(strings.ReplaceAll(strings.TrimSpace(raw), `\`, "/"), "/") {
		switch s {
		case "", ".":
			continue
		case "..":
			return "", fmt.Errorf("invalid folder %q: .. is not allowed", raw)
		}
		parts = append(parts, s)
	}
	return strings.Join(parts, "/"), nil
}

// relativeFolder is dir relative to the project root, in folder form ("" for
// the root itself or anything outside it).
func relativeFolder(projectDir, dir string) string {
	rel, err := filepath.Rel(projectDir, dir)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return ""
	}
	return filepath.ToSlash(rel)
}

// pickFolder returns the deepest folder that is rel or one of its parents.
func pickFolder(folders []string, rel string) string {
	best := ""
	for _, f := range folders {
		if f != "" && (rel == f || strings.HasPrefix(rel, f+"/")) && len(f) > len(best) {
			best = f
		}
	}
	return best
}

// folders lists the places that hold a .env. Servers without folder support
// have only the root.
func (t *target) folders(ctx context.Context) ([]string, error) {
	folders, err := t.client.Folders(ctx, t.project.ProjectID)
	var apiErr *api.Error
	if errors.As(err, &apiErr) && apiErr.Status == http.StatusNotFound && apiErr.Code != "project_not_found" {
		return []string{""}, nil
	}
	return folders, err
}

// resolveFolder sets the target's folder from --path or the working directory.
func (t *target) resolveFolder(ctx context.Context, flag *folderFlag) error {
	if flag.set {
		t.ref.Folder = flag.value
		return nil
	}
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	rel := relativeFolder(t.projectDir(), cwd)
	folders, err := t.folders(ctx)
	if err != nil {
		return err
	}
	folder, err := chooseFolder(folders, rel)
	if err != nil {
		return err
	}
	t.ref.Folder = folder
	return nil
}

// chooseFolder picks the .env location for the working directory rel.
func chooseFolder(folders []string, rel string) (string, error) {
	if picked := pickFolder(folders, rel); picked != "" || slices.Contains(folders, "") {
		return picked, nil
	}
	switch len(folders) {
	case 0:
		return "", errors.New("the project has no .env yet; add one on the project page")
	case 1:
		return folders[0], nil
	}
	names := make([]string, len(folders))
	for i, f := range folders {
		names[i] = f + "/.env"
	}
	return "", usagef("no .env here (the project has %s); choose one with --path, or use --all",
		strings.Join(names, ", "))
}

// atRoot reports whether the working directory is the project root.
func (t *target) atRoot() bool {
	cwd, err := os.Getwd()
	if err != nil {
		return false
	}
	rel, err := filepath.Rel(t.projectDir(), cwd)
	return err == nil && rel == "."
}

// projectDir is the directory holding envo.yaml (the root folder).
func (t *target) projectDir() string {
	return filepath.Dir(t.project.Path)
}

// localFile is where a folder's .env lives in the working copy.
func (t *target) localFile(folder string) string {
	return filepath.Join(t.projectDir(), filepath.FromSlash(folder), ".env")
}

// label names the environment and, outside the root, the folder.
func (t *target) label() string {
	if t.ref.Folder == "" {
		return t.env.Slug
	}
	return fmt.Sprintf("%s (%s/.env)", t.env.Slug, t.ref.Folder)
}

// display shortens a path relative to the working directory for messages.
func display(path string) string {
	cwd, err := os.Getwd()
	if err != nil {
		return path
	}
	if rel, err := filepath.Rel(cwd, path); err == nil {
		return rel
	}
	return path
}
