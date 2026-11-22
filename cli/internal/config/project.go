// Package config handles envo.yaml (the per-repository project link), the
// per-user settings file and stored credentials.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// ProjectFile is the name of the project link file written by `envo init`.
const ProjectFile = "envo.yaml"

// ErrNoProject is returned when no envo.yaml is found.
var ErrNoProject = errors.New("no envo.yaml found in this directory or its parents; run `envo init` first")

// Project links a directory to an Envo project. It contains no secrets and is
// meant to be committed so the whole team shares it.
type Project struct {
	APIURL             string `yaml:"api_url,omitempty"`
	Organization       string `yaml:"organization"`
	OrganizationID     string `yaml:"organization_id"`
	Project            string `yaml:"project"`
	ProjectID          string `yaml:"project_id"`
	DefaultEnvironment string `yaml:"default_environment"`

	// Path is the file the project was loaded from (not serialized).
	Path string `yaml:"-"`
}

const projectHeader = "# Envo project link, written by `envo init`. Safe to commit: contains no secrets.\n"

// FindProject looks for envo.yaml in dir and its parents.
func FindProject(dir string) (*Project, error) {
	dir, err := filepath.Abs(dir)
	if err != nil {
		return nil, err
	}
	for {
		path := filepath.Join(dir, ProjectFile)
		if _, err := os.Stat(path); err == nil {
			return LoadProject(path)
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return nil, ErrNoProject
		}
		dir = parent
	}
}

// LoadProject reads and validates an envo.yaml file.
func LoadProject(path string) (*Project, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var p Project
	if err := yaml.Unmarshal(data, &p); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if p.OrganizationID == "" || p.ProjectID == "" {
		return nil, fmt.Errorf("%s: organization_id and project_id are required; run `envo init --force`", path)
	}
	if p.DefaultEnvironment == "" {
		p.DefaultEnvironment = "development"
	}
	p.Path = path
	return &p, nil
}

// SaveProject writes envo.yaml into dir.
func SaveProject(dir string, p *Project) (string, error) {
	data, err := yaml.Marshal(p)
	if err != nil {
		return "", err
	}
	path := filepath.Join(dir, ProjectFile)
	if err := os.WriteFile(path, append([]byte(projectHeader), data...), 0o644); err != nil {
		return "", err
	}
	return path, nil
}
