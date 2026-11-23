# CI/CD examples

`github-actions.yml` and `gitlab-ci.yml` show the same pipeline: install the
`envo` CLI, check access, run tests with the staging configuration and deploy
with production's. The variables only exist in the environment of the command
started by `envo run`; no `.env` file is written.

## Setup

1. **Link the repository.** Run `envo init --project <group>/<project>` and
   commit the resulting `envo.yaml`. It holds no secrets; CI uses its
   `project_id` and `api_url`.
2. **Create a service token.** On the project page in Envo, under *Service
   tokens*, create a token per pipeline and environment scope, e.g. a
   read-only token for `staging` for tests and a separate one for `production`
   for deployments. Prefer an expiry; the token is shown once.
3. **Store the token** as `ENVO_TOKEN`:
   - GitHub: a repository secret, or an *environment* secret for the
     production token so only the `deploy` job can read it.
   - GitLab: a CI/CD variable marked *Masked* and *Protected*; protected
     variables reach protected branches only.
4. **Publish the CLI** and set `ENVO_CLI_URL` to the location of the files
   built by `cli/scripts/build-release.sh` (binaries plus `SHA256SUMS`, which
   the examples verify). Any static file host works, e.g. a release page or an
   internal object store.

## Checks

- `envo whoami` prints the token's project, environments and whether it can
  write, so a mis-scoped token fails early.
- A token only sees its own environments: other environments do not exist for
  it, writes need the write permission, and every change it makes is recorded
  under the token's name in the environment history and audit log.
- If a token leaks, revoke it on the project page; it stops working at once.
