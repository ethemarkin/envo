package commands

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"envo/cli/internal/api"
	"envo/cli/internal/config"
)

func runInit(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "init", "init [--org SLUG] [--project SLUG] [--env SLUG] [--force] [--yes]")
	orgSlug := fs.String("org", "", "organization slug")
	projectSlug := fs.String("project", "", "project slug")
	envSlug := fs.String("env", "", "default environment slug (default: development)")
	force := fs.Bool("force", false, "overwrite an existing envo.yaml")
	yes := fs.Bool("yes", false, "answer yes to prompts (add .env to .gitignore)")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}

	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	if _, err := os.Stat(filepath.Join(cwd, config.ProjectFile)); err == nil && !*force {
		return fmt.Errorf("%s already exists; use --force to relink", config.ProjectFile)
	}

	client, err := a.client(nil)
	if err != nil {
		return err
	}

	orgs, err := client.Organizations(ctx)
	if err != nil {
		return err
	}
	org, err := pick(a, "Organization", orgs, *orgSlug,
		func(o api.Organization) string { return o.Slug },
		func(o api.Organization) string { return fmt.Sprintf("%s (%s)", o.Name, o.Slug) })
	if err != nil {
		return err
	}

	projects, err := client.Projects(ctx, org.ID)
	if err != nil {
		return err
	}
	project, err := pick(a, "Project", projects, *projectSlug,
		func(p api.Project) string { return p.Slug },
		func(p api.Project) string { return fmt.Sprintf("%s (%s)", p.Name, p.Slug) })
	if err != nil {
		return err
	}

	envs, err := client.Environments(ctx, org.ID, project.ID)
	if err != nil {
		return err
	}
	defaultEnv := *envSlug
	if defaultEnv == "" {
		defaultEnv = "development"
		if !hasEnv(envs, defaultEnv) && len(envs) > 0 {
			defaultEnv = envs[0].Slug
		}
	} else if !hasEnv(envs, defaultEnv) {
		return fmt.Errorf("environment %q not found in %s/%s", defaultEnv, org.Slug, project.Slug)
	}

	path, err := config.SaveProject(cwd, &config.Project{
		APIURL:             client.BaseURL,
		Organization:       org.Slug,
		OrganizationID:     org.ID,
		Project:            project.Slug,
		ProjectID:          project.ID,
		DefaultEnvironment: defaultEnv,
	})
	if err != nil {
		return err
	}
	a.io.printf("Linked to %s/%s (default environment: %s). Wrote %s.\n",
		org.Slug, project.Slug, defaultEnv, path)
	a.io.printf("envo.yaml contains no secrets; commit it so your team shares the link.\n")

	return ensureGitignored(a, cwd, *yes)
}

func hasEnv(envs []api.Environment, slug string) bool {
	for _, e := range envs {
		if e.Slug == slug {
			return true
		}
	}
	return false
}

// pick selects an item by slug, automatically when there is only one, or
// interactively from a numbered list.
func pick[T any](a *app, kind string, items []T, slug string, slugOf, label func(T) string) (T, error) {
	var zero T
	if slug != "" {
		for _, it := range items {
			if slugOf(it) == slug {
				return it, nil
			}
		}
		return zero, fmt.Errorf("%s %q not found", strings.ToLower(kind), slug)
	}
	switch len(items) {
	case 0:
		return zero, fmt.Errorf("no %ss found; create one in the dashboard first", strings.ToLower(kind))
	case 1:
		return items[0], nil
	}
	if !a.io.IsTerm {
		slugs := make([]string, len(items))
		for i, it := range items {
			slugs[i] = slugOf(it)
		}
		return zero, usagef("several %ss available, pass --%s (one of: %s)",
			strings.ToLower(kind), map[string]string{"Organization": "org", "Project": "project"}[kind],
			strings.Join(slugs, ", "))
	}
	labels := make([]string, len(items))
	for i, it := range items {
		labels[i] = label(it)
	}
	i, err := a.io.choose(kind+":", labels)
	if err != nil {
		return zero, err
	}
	return items[i], nil
}

// ensureGitignored offers to add .env to .gitignore when it is not ignored.
func ensureGitignored(a *app, dir string, yes bool) error {
	path := filepath.Join(dir, ".gitignore")
	if gitignoreCoversDotenv(path) {
		return nil
	}
	add := yes
	if !add && a.io.IsTerm {
		var err error
		if add, err = a.io.confirm(".env is not in .gitignore. Add it?", true); err != nil {
			return err
		}
	}
	if !add {
		a.io.printf("Note: add .env to .gitignore so pulled secrets are never committed.\n")
		return nil
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	prefix := ""
	if data, err := os.ReadFile(path); err == nil && len(data) > 0 && data[len(data)-1] != '\n' {
		prefix = "\n"
	}
	if _, err := f.WriteString(prefix + "# Local environment (envo pull)\n.env\n"); err != nil {
		return err
	}
	a.io.printf("Added .env to .gitignore.\n")
	return nil
}

func gitignoreCoversDotenv(path string) bool {
	f, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return false
	}
	if err != nil {
		return true // do not touch a file we cannot read
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		switch strings.TrimSpace(scanner.Text()) {
		case ".env", "/.env", ".env*", "*.env", "**/.env":
			return true
		}
	}
	return false
}
