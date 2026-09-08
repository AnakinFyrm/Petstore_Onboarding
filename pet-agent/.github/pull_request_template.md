## What and why

<!-- One or two sentences, plus the issue this closes. -->

## Checklist

- [ ] `make check` and `make test` pass locally
- [ ] The behaviour change is covered by a test
- [ ] Docs updated (`docs/`, README) if behaviour, configuration or runbooks changed
- [ ] New settings are in `.env.example`, and in `.env.shared` when they are cross-profile defaults
- [ ] `init.sql` changes are idempotent and safe to re-apply to an existing database
- [ ] Every commit and the PR title are conventional commits; they become the changelog
