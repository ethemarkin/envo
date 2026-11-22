package commands

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"envo/cli/internal/api"
	"envo/cli/internal/config"
)

func runLogin(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "login", "login [--api-url URL] [--no-browser]")
	apiURLFlag := fs.String("api-url", "", "Envo server URL")
	noBrowser := fs.Bool("no-browser", false, "do not open a browser, only print the URL")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}

	user, err := config.LoadUser()
	if err != nil {
		return err
	}
	cwd, _ := os.Getwd()
	project, _ := config.FindProject(cwd)
	apiURL := config.ResolveAPIURL(*apiURLFlag, project, user)
	client := api.New(apiURL)

	host, _ := os.Hostname()
	start, err := client.StartLogin(ctx, host)
	if err != nil {
		return err
	}

	a.io.printf("To sign in, open this page in your browser and enter the code:\n\n")
	a.io.printf("  %s\n\n", start.VerificationURI)
	a.io.printf("  Code: %s\n\n", start.UserCode)
	if !*noBrowser {
		if err := openBrowser(start.VerificationURI); err != nil {
			a.io.printf("(Could not open a browser; open the link manually.)\n")
		}
	}
	a.io.printf("Waiting for approval...\n")

	tokens, err := pollLogin(ctx, client, start)
	if err != nil {
		return err
	}

	store, err := a.credentialStore()
	if err != nil {
		return err
	}
	if err := store.Save(apiURL, tokens.Credentials()); err != nil {
		return fmt.Errorf("saving credentials: %w", err)
	}
	user.APIURL, user.Email = apiURL, tokens.User.Email
	if err := config.SaveUser(user); err != nil {
		return err
	}
	a.io.printf("Logged in to %s as %s.\n", apiURL, tokens.User.Email)
	return nil
}

func pollLogin(ctx context.Context, client *api.Client, start *api.LoginStart) (*api.TokenResponse, error) {
	interval := time.Duration(max(start.Interval, 1)) * time.Second
	deadline := time.Now().Add(time.Duration(start.ExpiresIn) * time.Second)
	for time.Now().Before(deadline) {
		select {
		case <-ctx.Done():
			return nil, errAborted
		case <-time.After(interval):
		}
		tokens, err := client.PollLogin(ctx, start.DeviceCode)
		if err == nil {
			return tokens, nil
		}
		var apiErr *api.Error
		if !errors.As(err, &apiErr) {
			return nil, err
		}
		switch apiErr.Code {
		case "authorization_pending":
			continue
		case "slow_down":
			interval += time.Second
		case "access_denied":
			return nil, errors.New("the login request was denied in the browser")
		case "expired_token":
			return nil, errors.New("the login request expired; run `envo login` again")
		default:
			return nil, err
		}
	}
	return nil, errors.New("the login request expired; run `envo login` again")
}

func runLogout(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "logout", "logout")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}
	user, err := config.LoadUser()
	if err != nil {
		return err
	}
	cwd, _ := os.Getwd()
	project, _ := config.FindProject(cwd)
	apiURL := config.ResolveAPIURL("", project, user)
	store, err := a.credentialStore()
	if err != nil {
		return err
	}
	creds, err := store.Load(apiURL)
	if errors.Is(err, config.ErrNotLoggedIn) {
		a.io.printf("Not logged in to %s.\n", apiURL)
		return nil
	}
	if err != nil {
		return err
	}
	// Revoke on the server first; local credentials go away either way.
	if err := api.New(apiURL).Logout(ctx, creds.RefreshToken); err != nil {
		a.io.printf("Warning: could not revoke the session on the server: %v\n", err)
	}
	if err := store.Delete(apiURL); err != nil {
		return err
	}
	a.io.printf("Logged out of %s.\n", apiURL)
	return nil
}

func runWhoami(ctx context.Context, a *app, args []string) error {
	fs := newFlags(a, "whoami", "whoami")
	if _, _, err := parseInterspersed(fs, args); err != nil {
		return err
	}
	cwd, _ := os.Getwd()
	project, _ := config.FindProject(cwd)
	client, err := a.client(project)
	if err != nil {
		return err
	}
	me, err := client.Me(ctx)
	if err != nil {
		return err
	}
	fmt.Fprintf(a.io.Out, "%s\n", me.Email)
	a.io.printf("Server: %s\n", client.BaseURL)
	return nil
}
