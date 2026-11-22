package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/zalando/go-keyring"
)

// Credentials are the CLI's session tokens for one Envo server.
type Credentials struct {
	AccessToken     string    `json:"access_token"`
	RefreshToken    string    `json:"refresh_token"`
	AccessExpiresAt time.Time `json:"access_expires_at"`
	Email           string    `json:"email,omitempty"`
}

// ErrNotLoggedIn is returned when no credentials are stored for a server.
var ErrNotLoggedIn = errors.New("not logged in; run `envo login`")

// CredentialStore persists credentials per server URL.
type CredentialStore interface {
	Load(apiURL string) (*Credentials, error)
	Save(apiURL string, c *Credentials) error
	Delete(apiURL string) error
	Name() string
}

const keyringService = "envo"

// KeyringStore keeps credentials in the operating system's keychain
// (Windows Credential Manager, macOS Keychain, Secret Service on Linux).
type KeyringStore struct{}

func (KeyringStore) Name() string { return "system keychain" }

func (KeyringStore) Load(apiURL string) (*Credentials, error) {
	secret, err := keyring.Get(keyringService, apiURL)
	if errors.Is(err, keyring.ErrNotFound) {
		return nil, ErrNotLoggedIn
	}
	if err != nil {
		return nil, err
	}
	var c Credentials
	if err := json.Unmarshal([]byte(secret), &c); err != nil {
		return nil, err
	}
	return &c, nil
}

func (KeyringStore) Save(apiURL string, c *Credentials) error {
	data, err := json.Marshal(c)
	if err != nil {
		return err
	}
	return keyring.Set(keyringService, apiURL, string(data))
}

func (KeyringStore) Delete(apiURL string) error {
	err := keyring.Delete(keyringService, apiURL)
	if errors.Is(err, keyring.ErrNotFound) {
		return nil
	}
	return err
}

// FileStore keeps credentials in a 0600 JSON file in the config directory.
// Used when no keychain is available (headless Linux, containers) or when
// ENVO_CREDENTIALS_STORE=file.
type FileStore struct{ Path string }

func (s FileStore) Name() string { return s.Path }

func (s FileStore) readAll() (map[string]*Credentials, error) {
	all := map[string]*Credentials{}
	data, err := os.ReadFile(s.Path)
	if errors.Is(err, os.ErrNotExist) {
		return all, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(data, &all); err != nil {
		return nil, err
	}
	return all, nil
}

func (s FileStore) writeAll(all map[string]*Credentials) error {
	data, err := json.MarshalIndent(all, "", "  ")
	if err != nil {
		return err
	}
	tmp := s.Path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, s.Path)
}

func (s FileStore) Load(apiURL string) (*Credentials, error) {
	all, err := s.readAll()
	if err != nil {
		return nil, err
	}
	c, ok := all[apiURL]
	if !ok {
		return nil, ErrNotLoggedIn
	}
	return c, nil
}

func (s FileStore) Save(apiURL string, c *Credentials) error {
	all, err := s.readAll()
	if err != nil {
		return err
	}
	all[apiURL] = c
	return s.writeAll(all)
}

func (s FileStore) Delete(apiURL string) error {
	all, err := s.readAll()
	if err != nil {
		return err
	}
	delete(all, apiURL)
	return s.writeAll(all)
}

// fallbackStore uses the keychain and falls back to the file store when the
// keychain is unavailable.
type fallbackStore struct {
	primary  CredentialStore
	fallback CredentialStore
}

func (f fallbackStore) Name() string { return f.primary.Name() }

func (f fallbackStore) Load(apiURL string) (*Credentials, error) {
	c, err := f.primary.Load(apiURL)
	if err == nil {
		return c, nil
	}
	if fc, ferr := f.fallback.Load(apiURL); ferr == nil {
		return fc, nil
	}
	return nil, err
}

func (f fallbackStore) Save(apiURL string, c *Credentials) error {
	if err := f.primary.Save(apiURL, c); err != nil {
		return f.fallback.Save(apiURL, c)
	}
	// Do not leave an older copy behind in the file.
	_ = f.fallback.Delete(apiURL)
	return nil
}

func (f fallbackStore) Delete(apiURL string) error {
	err1 := f.primary.Delete(apiURL)
	err2 := f.fallback.Delete(apiURL)
	if err1 != nil && err2 != nil {
		return err1
	}
	return nil
}

// NewCredentialStore returns the store selected by ENVO_CREDENTIALS_STORE
// ("keychain" or "file"); by default the keychain with a file fallback.
func NewCredentialStore() (CredentialStore, error) {
	dir, err := Dir()
	if err != nil {
		return nil, err
	}
	file := FileStore{Path: filepath.Join(dir, "credentials.json")}
	switch os.Getenv("ENVO_CREDENTIALS_STORE") {
	case "file":
		return file, nil
	case "keychain":
		return KeyringStore{}, nil
	default:
		return fallbackStore{primary: KeyringStore{}, fallback: file}, nil
	}
}
