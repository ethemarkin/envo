package commands

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"

	"golang.org/x/term"
)

// IO bundles the streams a command uses, so tests can drive commands.
type IO struct {
	In     io.Reader
	Out    io.Writer // data (pull --output -), command results
	Err    io.Writer // status messages and prompts
	IsTerm bool      // stdin is an interactive terminal

	reader *bufio.Reader
}

func stdIO() *IO {
	return &IO{
		In:     os.Stdin,
		Out:    os.Stdout,
		Err:    os.Stderr,
		IsTerm: term.IsTerminal(int(os.Stdin.Fd())),
	}
}

var errAborted = errors.New("aborted")

func (s *IO) printf(format string, args ...any) {
	fmt.Fprintf(s.Err, format, args...)
}

// lines returns one shared buffered reader, so consecutive prompts do not
// lose input that an earlier read already buffered.
func (s *IO) lines() *bufio.Reader {
	if s.reader == nil {
		s.reader = bufio.NewReader(s.In)
	}
	return s.reader
}

func (s *IO) readLine() (string, error) {
	line, err := s.lines().ReadString('\n')
	if err != nil && !(errors.Is(err, io.EOF) && line != "") {
		return "", err
	}
	return strings.TrimRight(line, "\r\n"), nil
}

// confirm asks a yes/no question; defaultYes decides on an empty answer.
func (s *IO) confirm(question string, defaultYes bool) (bool, error) {
	hint := "[y/N]"
	if defaultYes {
		hint = "[Y/n]"
	}
	s.printf("%s %s ", question, hint)
	answer, err := s.readLine()
	if err != nil {
		return false, err
	}
	switch strings.ToLower(strings.TrimSpace(answer)) {
	case "":
		return defaultYes, nil
	case "y", "yes", "e", "evet":
		return true, nil
	default:
		return false, nil
	}
}

// choose shows a numbered list and returns the selected index.
func (s *IO) choose(title string, options []string) (int, error) {
	s.printf("%s\n", title)
	for i, o := range options {
		s.printf("  %d) %s\n", i+1, o)
	}
	for {
		s.printf("Select 1-%d: ", len(options))
		line, err := s.readLine()
		if err != nil {
			return 0, err
		}
		n, err := strconv.Atoi(strings.TrimSpace(line))
		if err == nil && n >= 1 && n <= len(options) {
			return n - 1, nil
		}
	}
}

// readSecret reads a value without echoing it when stdin is a terminal.
func (s *IO) readSecret(prompt string) (string, error) {
	if f, ok := s.In.(*os.File); ok && s.IsTerm {
		s.printf("%s", prompt)
		data, err := term.ReadPassword(int(f.Fd()))
		s.printf("\n")
		return string(data), err
	}
	data, err := io.ReadAll(s.lines())
	if err != nil {
		return "", err
	}
	// `echo value | envo set KEY` adds one newline; drop exactly that.
	value := strings.TrimSuffix(string(data), "\n")
	return strings.TrimSuffix(value, "\r"), nil
}

// openBrowser tries to open url in the default browser.
func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}
