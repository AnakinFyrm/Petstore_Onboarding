# Decisions

Architecture decision records for pet-agent: the choices that outlive the pull
request that made them.

Write one when a decision would otherwise only be explained in a code review — a rejected
alternative, a deliberate limitation, a dependency taken on for a reason that is not
obvious from the import. Do not write one for something the code already says.

## How

Copy [0000-adr-template.md](0000-adr-template.md) to `NNNN-short-slug.md` with the next
free number and fill in the four sections. Keep it to about twenty lines: Context is the
constraint and the alternatives that were genuinely on the table, Decision is what we now
do, Consequences is what it costs.

Numbers are sequential and never reused. A decision that gets reversed is a *new* ADR
that marks the old one `superseded by`, not an edit — the record of having believed
something else is the useful part.

The directory listing is the index; there is no tooling to keep in sync.

## Records

- [0000-adr-template.md](0000-adr-template.md) — the template itself
- [0001-generated-from-fyrm-template-gen.md](0001-generated-from-fyrm-template-gen.md)
