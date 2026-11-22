// Package api is the Envo HTTP API client used by the CLI.
package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"envo/cli/internal/config"
)

// Error is a non-2xx API response. Code is the backend's machine-readable
// `detail`; Body keeps the full JSON (e.g. `errors` for .env parse failures).
type Error struct {
	Status int
	Code   string
	Body   map[string]any
}

func (e *Error) Error() string {
	if msg, ok := messages[e.Code]; ok {
		return msg
	}
	return fmt.Sprintf("request failed (%d %s)", e.Status, e.Code)
}

// Keys returns the `keys` field of a validation error, if any.
func (e *Error) Keys() []string {
	raw, _ := e.Body["keys"].([]any)
	keys := make([]string, 0, len(raw))
	for _, k := range raw {
		if s, ok := k.(string); ok {
			keys = append(keys, s)
		}
	}
	return keys
}

var messages = map[string]string{
	"not_authenticated":         "not logged in or session expired; run `envo login`",
	"invalid_refresh_token":     "session expired; run `envo login`",
	"refresh_token_reused":      "session was revoked; run `envo login`",
	"forbidden":                 "you do not have permission for this in this environment",
	"organization_not_found":    "organization not found or you are not a member",
	"project_not_found":         "project not found",
	"environment_not_found":     "environment not found",
	"variable_not_found":        "variable not found",
	"invalid_key":               "invalid key: use letters, digits and underscores, not starting with a digit",
	"value_too_long":            "value is too long (max 64 KiB)",
	"invalid_dotenv":            "the .env file has errors",
	"encryption_not_configured": "the server has no encryption key configured",
	"revision_conflict":         "the environment changed in the meantime; try again",
}

// Client talks to one Envo server. Requests carry a bearer token; expired
// access tokens are refreshed with the stored refresh token and saved back.
type Client struct {
	BaseURL string
	HTTP    *http.Client

	store       config.CredentialStore
	creds       *config.Credentials
	staticToken string
	mu          sync.Mutex
}

// New creates an unauthenticated client.
func New(baseURL string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTP:    &http.Client{Timeout: 60 * time.Second},
	}
}

// WithCredentials authenticates with stored, refreshable credentials.
func (c *Client) WithCredentials(store config.CredentialStore, creds *config.Credentials) *Client {
	c.store, c.creds = store, creds
	return c
}

// WithToken authenticates with a fixed bearer token (ENVO_TOKEN in CI).
func (c *Client) WithToken(token string) *Client {
	c.staticToken = token
	return c
}

const refreshSkew = 30 * time.Second

func (c *Client) accessToken(ctx context.Context, forceRefresh bool) (string, error) {
	if c.staticToken != "" {
		return c.staticToken, nil
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.creds == nil {
		return "", nil
	}
	if forceRefresh || time.Until(c.creds.AccessExpiresAt) < refreshSkew {
		if err := c.refreshLocked(ctx); err != nil {
			return "", err
		}
	}
	return c.creds.AccessToken, nil
}

func (c *Client) refreshLocked(ctx context.Context) error {
	var out TokenResponse
	err := c.send(ctx, http.MethodPost, "/api/cli/auth/refresh", "",
		map[string]string{"refresh_token": c.creds.RefreshToken}, &out, nil)
	if err != nil {
		var apiErr *Error
		if errors.As(err, &apiErr) && apiErr.Status == http.StatusUnauthorized {
			if c.store != nil {
				_ = c.store.Delete(c.BaseURL)
			}
			return &Error{Status: 401, Code: "invalid_refresh_token"}
		}
		return err
	}
	c.creds = out.Credentials()
	if c.store != nil {
		if err := c.store.Save(c.BaseURL, c.creds); err != nil {
			return fmt.Errorf("saving refreshed credentials: %w", err)
		}
	}
	return nil
}

// Do sends an authenticated JSON request and decodes the JSON response into out.
func (c *Client) Do(ctx context.Context, method, path string, body, out any) error {
	return c.do(ctx, method, path, body, out, nil)
}

func (c *Client) do(ctx context.Context, method, path string, body, out any, raw *[]byte) error {
	token, err := c.accessToken(ctx, false)
	if err != nil {
		return err
	}
	err = c.send(ctx, method, path, token, body, out, raw)
	var apiErr *Error
	if errors.As(err, &apiErr) && apiErr.Status == http.StatusUnauthorized &&
		c.creds != nil && c.staticToken == "" {
		if token, err = c.accessToken(ctx, true); err != nil {
			return err
		}
		return c.send(ctx, method, path, token, body, out, raw)
	}
	return err
}

func (c *Client) send(ctx context.Context, method, path, token string, body, out any, raw *[]byte) error {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "envo-cli")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	res, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("cannot reach Envo at %s: %w", c.BaseURL, err)
	}
	defer res.Body.Close()
	data, err := io.ReadAll(res.Body)
	if err != nil {
		return err
	}
	if res.StatusCode >= 300 {
		apiErr := &Error{Status: res.StatusCode, Code: fmt.Sprintf("http_%d", res.StatusCode)}
		if json.Unmarshal(data, &apiErr.Body) == nil {
			if code, ok := apiErr.Body["detail"].(string); ok {
				apiErr.Code = code
			}
		}
		return apiErr
	}
	if raw != nil {
		*raw = data
		return nil
	}
	if out != nil && len(data) > 0 {
		return json.Unmarshal(data, out)
	}
	return nil
}

// --- Auth ---------------------------------------------------------------------

type User struct {
	ID    string `json:"id"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

type LoginStart struct {
	DeviceCode      string `json:"device_code"`
	UserCode        string `json:"user_code"`
	VerificationURI string `json:"verification_uri"`
	ExpiresIn       int    `json:"expires_in"`
	Interval        int    `json:"interval"`
}

type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
	User         User   `json:"user"`
}

// Credentials converts a token response into storable credentials.
func (t *TokenResponse) Credentials() *config.Credentials {
	return &config.Credentials{
		AccessToken:     t.AccessToken,
		RefreshToken:    t.RefreshToken,
		AccessExpiresAt: time.Now().Add(time.Duration(t.ExpiresIn) * time.Second),
		Email:           t.User.Email,
	}
}

func (c *Client) StartLogin(ctx context.Context, clientName string) (*LoginStart, error) {
	var out LoginStart
	err := c.send(ctx, http.MethodPost, "/api/cli/auth/start", "",
		map[string]string{"client_name": clientName}, &out, nil)
	return &out, err
}

// PollLogin returns the tokens, or an *Error with Code "authorization_pending",
// "access_denied", "expired_token" or "invalid_grant".
func (c *Client) PollLogin(ctx context.Context, deviceCode string) (*TokenResponse, error) {
	var out TokenResponse
	err := c.send(ctx, http.MethodPost, "/api/cli/auth/token", "",
		map[string]string{"device_code": deviceCode}, &out, nil)
	return &out, err
}

func (c *Client) Logout(ctx context.Context, refreshToken string) error {
	return c.send(ctx, http.MethodPost, "/api/cli/auth/logout", "",
		map[string]string{"refresh_token": refreshToken}, nil, nil)
}

func (c *Client) Me(ctx context.Context) (*User, error) {
	var out User
	return &out, c.Do(ctx, http.MethodGet, "/api/auth/me", nil, &out)
}

// --- Organizations, projects, environments ------------------------------------

type Organization struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Slug string `json:"slug"`
	Role string `json:"role"`
}

type Project struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Slug string `json:"slug"`
}

type Environment struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Slug      string `json:"slug"`
	Protected bool   `json:"protected"`
	Revision  int    `json:"revision"`
}

func (c *Client) Organizations(ctx context.Context) ([]Organization, error) {
	var out []Organization
	return out, c.Do(ctx, http.MethodGet, "/api/orgs", nil, &out)
}

func (c *Client) Projects(ctx context.Context, orgID string) ([]Project, error) {
	var out []Project
	return out, c.Do(ctx, http.MethodGet, "/api/orgs/"+url.PathEscape(orgID)+"/projects", nil, &out)
}

func projectPath(orgID, projectID string) string {
	return "/api/orgs/" + url.PathEscape(orgID) + "/projects/" + url.PathEscape(projectID)
}

func (c *Client) Environments(ctx context.Context, orgID, projectID string) ([]Environment, error) {
	var out []Environment
	return out, c.Do(ctx, http.MethodGet, projectPath(orgID, projectID)+"/environments", nil, &out)
}

// --- Variables -------------------------------------------------------------------

// EnvRef identifies one environment.
type EnvRef struct {
	OrgID, ProjectID, EnvID string
}

func (r EnvRef) path() string {
	return projectPath(r.OrgID, r.ProjectID) + "/environments/" + url.PathEscape(r.EnvID)
}

// ExportJSON returns every variable of the environment in plain text.
func (c *Client) ExportJSON(ctx context.Context, env EnvRef) (map[string]string, error) {
	out := map[string]string{}
	return out, c.Do(ctx, http.MethodGet, env.path()+"/export?format=json", nil, &out)
}

// ExportDotenv returns the environment as a .env document.
func (c *Client) ExportDotenv(ctx context.Context, env EnvRef) ([]byte, error) {
	var raw []byte
	return raw, c.do(ctx, http.MethodGet, env.path()+"/export", nil, nil, &raw)
}

type ImportItem struct {
	Key        string `json:"key"`
	Status     string `json:"status"`
	Visibility string `json:"visibility"`
}

type ImportResult struct {
	Revision int          `json:"revision"`
	DryRun   bool         `json:"dry_run"`
	Items    []ImportItem `json:"items"`
}

type DotenvError struct {
	Line    int    `json:"line"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

// DotenvErrors extracts parse errors from an "invalid_dotenv" API error.
func DotenvErrors(err error) []DotenvError {
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Code != "invalid_dotenv" {
		return nil
	}
	data, _ := json.Marshal(apiErr.Body["errors"])
	var out []DotenvError
	_ = json.Unmarshal(data, &out)
	return out
}

func (c *Client) Import(
	ctx context.Context, env EnvRef, content string, visibility map[string]string, dryRun bool,
) (*ImportResult, error) {
	var out ImportResult
	body := map[string]any{"content": content, "visibility": visibility, "dry_run": dryRun}
	return &out, c.Do(ctx, http.MethodPost, env.path()+"/import", body, &out)
}

type WriteResult struct {
	Revision int      `json:"revision"`
	Created  []string `json:"created"`
	Updated  []string `json:"updated"`
	Deleted  []string `json:"deleted"`
}

func (c *Client) SetVariable(
	ctx context.Context, env EnvRef, key, value, visibility string,
) (*WriteResult, error) {
	body := map[string]any{"value": value}
	if visibility != "" {
		body["visibility"] = visibility
	}
	var out WriteResult
	return &out, c.Do(ctx, http.MethodPut, env.path()+"/variables/"+url.PathEscape(key), body, &out)
}
