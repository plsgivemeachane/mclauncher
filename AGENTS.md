## Agent skills

### Issue tracker

Local Markdown issues under `.scratch/<feature>/`.
See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage roles.
See `docs/agents/triage-labels.md`.

### Domain docs

Single-context glossary and ADR layout.
See `docs/agents/domain.md`.

## Release trigger

When the user says “commit, push, build a new version, gimme apt command with full path”, follow the [Ubuntu package workflow](packaging/README.md). Bump the patch version unless the user specifies another increment. Validate, commit, and push the requested changes, then build and verify the versioned amd64 package from that commit. Return the commit hash and a copyable `sudo apt install "/absolute/path/to/package.deb"` command using the actual package path.
