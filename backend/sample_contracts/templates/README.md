# Sample contract templates

These templates are the input of `scripts/generate_contracts.py`, which turns
them into realistic PDF contracts (dates are computed relative to the day the
script runs). They are **only** used by the generator: the ingestion pipeline
reads the generated PDFs and `metadata.json`, never these files.

All companies and people named here are fictional.

## Format

```
key: value           <- header (contract metadata)
...
===                  <- end of header
# Background         <- recitals, lettered (A), (B), ...
## Clause heading    <- a numbered clause (1., 2., ...)
Paragraph text       <- each paragraph is a sub-clause (1.1, 1.2, ...)
- list item          <- indented list item inside a paragraph
@include name        <- insert a shared clause from _boilerplate.txt
```

Placeholders: `{effective_date}`, `{expiration_date}`, `{initial_term}`,
`{company}`, `{counterparty}`, `{n}` (current clause number) and
`{ref:Heading}` (number of the clause with that heading).
