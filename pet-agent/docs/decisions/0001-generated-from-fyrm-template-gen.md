# 0001. pet-agent is generated from fyrm-template-gen

- Status: accepted
- Date: the day this repository was generated (fill in on the first commit)

## Context

A new fyrm project can be started three ways: copied from the nearest existing
repository, assembled by hand, or generated from the shared Copier template. Copying is
how the fleet ended up with four ruff configurations and three Dockerfile styles, each
diverging quietly from the others. Assembling by hand is a day of work that produces a
fourth variant.

## Decision

This project is generated from `fyrm-template-gen` as a **agent-service**, and stays
connected to it: `.copier-answers.yml` records the template version and the answers, and
`uvx copier update --trust` pulls later template improvements in as a reviewable diff.

Configuration that the template owns — the ruff and mypy settings, the CI workflows, the
Dockerfile, the pre-commit hook set — is not edited here. Changes to it are proposed
against the template so the whole fleet gets them.

## Consequences

Local edits to template-owned files come back as merge conflicts on the next
`copier update`. That friction is the mechanism: it makes drift visible instead of
permanent.

A convention that is wrong for this project has to be argued centrally rather than
patched locally, which is slower. Where a deviation is genuinely right, record it as its
own ADR next to this one so the next `copier update` conflict has an explanation.
