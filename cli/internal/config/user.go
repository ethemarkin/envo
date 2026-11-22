package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
)

// DefaultAPIURL is used when nothing else configures the server.
const DefaultAPIURL = "http://localhost:4400"

// User holds per-user, per-machine settings (never committed).
type User struct {
	APIURL string `json:"api_url,omitempty"`
	Email  string `json:"email,omitempty"`
}

// Dir returns the Envo configuration directory, creating it if needed.
// ENVO_CONFIG_DIR overrides the platform default.
func Dir() (string, error) {
	dir := os.Getenv("ENVO_CONFIG_DIR")
	if dir == "" {
		base, err := os.UserConfigDir()
		if err != nil {
			return "", err
		}
		dir = filepath.Join(base, "envo")
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

func userPath() (string, error) {
	dir, err := Dir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "config.json"), nil
}

// LoadUser reads the user settings; a missing file yields empty settings.
func LoadUser() (*User, error) {
	path, err := userPath()
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return &User{}, nil
	}
	if err != nil {
		return nil, err
	}
	var u User
	if err := json.Unmarshal(data, &u); err != nil {
		return nil, err
	}
	return &u, nil
}

// SaveUser writes the user settings.
func SaveUser(u *User) error {
	path, err := userPath()
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(u, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o600)
}

// ResolveAPIURL picks the server: explicit flag, ENVO_API_URL, envo.yaml,
// the URL used at login, then the default.
func ResolveAPIURL(flag string, project *Project, user *User) string {
	for _, candidate := range []string{
		flag,
		os.Getenv("ENVO_API_URL"),
		projectURL(project),
		userURL(user),
		DefaultAPIURL,
	} {
		if candidate != "" {
			return strings.TrimRight(candidate, "/")
		}
	}
	return DefaultAPIURL
}

func projectURL(p *Project) string {
	if p == nil {
		return ""
	}
	return p.APIURL
}

func userURL(u *User) string {
	if u == nil {
		return ""
	}
	return u.APIURL
}
