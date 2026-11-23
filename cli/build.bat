@echo off
rem Builds and tests the envo CLI.
rem
rem   build.bat                  build envo.exe for Windows (default)
rem   build.bat test             run the tests
rem   build.bat macos [VER]      build zips for macOS (Apple Silicon and Intel) into dist\
rem   build.bat release [VER]    build zips for every platform into dist\ with SHA256SUMS
rem
rem Each zip is named after its platform (e.g. envo-darwin-arm64.zip) and holds a
rem single binary called envo (envo.exe on Windows). VER defaults to "dev".
rem build and test use a local Go toolchain if one is installed, otherwise the
rem golang:1.26 Docker image; macos and release always run in Docker, since
rem scripts\build-release.sh needs sh and sha256sum.

setlocal
pushd "%~dp0"

set "TASK=%~1"
if "%TASK%"=="" set "TASK=build"

where go >nul 2>nul
if %ERRORLEVEL%==0 (set "USE_GO=1") else (set "USE_GO=0")

if /i "%TASK%"=="build" goto build
if /i "%TASK%"=="test" goto test
if /i "%TASK%"=="macos" goto macos
if /i "%TASK%"=="release" goto release
echo Unknown command: %TASK%
echo Usage: build.bat [build ^| test ^| macos [VERSION] ^| release [VERSION]]
set "RC=1"
goto end

:build
echo Building envo.exe...
if "%USE_GO%"=="1" (
  set "GOOS=windows"
  go build -o envo.exe ./cmd/envo
) else (
  docker run --rm -v "%CD%:/src" -w /src -e GOOS=windows golang:1.26 go build -o envo.exe ./cmd/envo
)
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo Done: %CD%\envo.exe
goto end

:test
if "%USE_GO%"=="1" (
  go test ./...
) else (
  docker run --rm -v "%CD%:/src" -w /src golang:1.26 go test ./...
)
set "RC=%ERRORLEVEL%"
goto end

:macos
set "TARGETS=darwin/arm64 darwin/amd64"
goto dist

:release
set "TARGETS="
goto dist

:dist
set "VERSION=%~2"
if "%VERSION%"=="" set "VERSION=dev"
docker run --rm -v "%CD%:/src" -w /src -e VERSION=%VERSION% -e "TARGETS=%TARGETS%" golang:1.26 sh scripts/build-release.sh
set "RC=%ERRORLEVEL%"
goto end

:end
popd
exit /b %RC%
