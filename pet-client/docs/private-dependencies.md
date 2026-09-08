# Depending on private repositories

If this project depends on another **private** GitHub repository — common when
installing an internal `fyrm-ai` library from a git source in
`pyproject.toml` — then every environment that installs dependencies needs read
access to that repo. Without it, `uv sync` fails with:

```
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

The default Actions `GITHUB_TOKEN` only grants access to *this* repo, so private
**cross-repo** dependencies need an explicit token. Set it up once for local
dev, CI and Dependabot.

## 1. Create a fine-grained Personal Access Token (PAT)

GitHub → *Settings → Developer settings → Fine-grained tokens → Generate new token*:

- **Resource owner**: your org (`fyrm-ai`) — required to see private org repos.
- **Repository access**: *Only select repositories* → the private dependency repo(s).
- **Permissions → Repository permissions → Contents: Read-only** (nothing else needed).
- Generate and copy the `github_pat_…` value.

> If your org disables fine-grained tokens, use a **classic** token with the
> `repo` scope (broader, but works). Fine-grained tokens for an org may need an
> owner to approve them.

## 2. Local development (`uv sync`)

Easiest — authenticate the GitHub CLI once; git reuses it:

```bash
gh auth login            # or: gh auth setup-git
```

Or point git at the PAT for all of github.com:

```bash
git config --global url."https://x-access-token:YOUR_TOKEN@github.com/".insteadOf "https://github.com/"
```

## 3. GitHub Actions (CI)

Add the token as a repo (or org) secret named **`GH_DEP_TOKEN`**:

```bash
gh secret set GH_DEP_TOKEN -R fyrm-ai/pet-client
# paste the github_pat_… value
```

The bundled `setup-python-env` action already passes this secret to git before
`uv sync`, so CI authenticates automatically — nothing else to wire up. If the
secret is absent (all-public deps), the auth step is skipped.

## 5. Dependabot

Dependabot also cannot resolve a private git dependency without access:

- **Grant access**: Org/Repo → *Settings → Code security → Dependabot* → grant
  access to the private dependency repo(s). Otherwise its weekly update run fails
  to resolve the dependency.
- **Enable alerts + automated security fixes** (recommended): same settings page,
  or via the API:

```bash
gh api -X PUT repos/fyrm-ai/pet-client/vulnerability-alerts
gh api -X PUT repos/fyrm-ai/pet-client/automated-security-fixes
```

## 6. The simplest alternative

Every step above exists *only* because the dependency is private. If you make
that repository **public**, or publish the library to a package registry, no
tokens, secrets, or access grants are needed anywhere.
