// Command zipdist packs one built binary into a zip archive for release.
//
//	go run ./scripts/zipdist dist/envo-darwin-arm64.zip build/envo
//
// The file is stored under its base name with Unix mode 0755, so it stays
// executable after unzipping on macOS and Linux even when built on Windows.
// The base Debian Go image has no zip tool, which is why this exists.
package main

import (
	"archive/zip"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: zipdist <out.zip> <file>")
		os.Exit(2)
	}
	if err := pack(os.Args[1], os.Args[2]); err != nil {
		fmt.Fprintln(os.Stderr, "zipdist:", err)
		os.Exit(1)
	}
}

func pack(out, file string) (err error) {
	src, err := os.Open(file)
	if err != nil {
		return err
	}
	defer src.Close()
	info, err := src.Stat()
	if err != nil {
		return err
	}

	dst, err := os.Create(out)
	if err != nil {
		return err
	}
	defer func() {
		if cerr := dst.Close(); err == nil {
			err = cerr
		}
	}()

	zw := zip.NewWriter(dst)
	header, err := zip.FileInfoHeader(info)
	if err != nil {
		return err
	}
	header.Name = filepath.Base(file)
	header.Method = zip.Deflate
	header.SetMode(0o755)
	w, err := zw.CreateHeader(header)
	if err != nil {
		return err
	}
	if _, err := io.Copy(w, src); err != nil {
		return err
	}
	return zw.Close()
}
