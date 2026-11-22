package commands

import (
	"bytes"
	"strings"
	"testing"
)

func TestRun(t *testing.T) {
	cases := []struct {
		args     []string
		code     int
		inStdout string
		inStderr string
	}{
		{nil, 0, "Usage:", ""},
		{[]string{"version"}, 0, "envo dev", ""},
		{[]string{"pull"}, 1, "", "not implemented"},
		{[]string{"bogus"}, 2, "", "unknown command"},
	}
	for _, tc := range cases {
		var out, errOut bytes.Buffer
		code := Run(tc.args, &out, &errOut)
		if code != tc.code {
			t.Errorf("Run(%v) = %d, want %d", tc.args, code, tc.code)
		}
		if !strings.Contains(out.String(), tc.inStdout) {
			t.Errorf("Run(%v) stdout %q missing %q", tc.args, out.String(), tc.inStdout)
		}
		if !strings.Contains(errOut.String(), tc.inStderr) {
			t.Errorf("Run(%v) stderr %q missing %q", tc.args, errOut.String(), tc.inStderr)
		}
	}
}
