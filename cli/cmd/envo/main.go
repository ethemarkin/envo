// Command envo is the Envo command-line client.
package main

import (
	"os"

	"envo/cli/internal/commands"
)

func main() {
	os.Exit(commands.Run(os.Args[1:], os.Stdout, os.Stderr))
}
