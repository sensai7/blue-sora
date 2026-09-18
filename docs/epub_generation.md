# EPUB generation

Milestone 8 produces one deterministic EPUB 3 file per reduced-corpus work at
`build/site/downloads/<stable-slug>.epub`. The regular site build runs EPUB
generation first, so each work page exposes its download only after the book
has passed validation.

## Package contents

Each publication contains:

- an uncompressed `mimetype` entry followed by a deterministic ZIP layout;
- EPUB 3 package metadata with stable work ID, Japanese title, authors,
  language, source URL, public-domain attribution, and modified timestamp;
- a generated accessible SVG cover placeholder;
- EPUB 3 navigation plus NCX navigation for older readers;
- spine-ordered XHTML chapters split at canonical headings;
- a source-and-edition colophon;
- local illustrations and gaiji copied from canonical ingestion; and
- a reflowable vertical-rl Japanese stylesheet with ruby support.

All ZIP timestamps and entry ordering are fixed. Rebuilding identical inputs
therefore produces identical bytes, and existing books are not rewritten.

## Validation

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_epubs.py
```

The built-in EPUB 3 conformance validator checks the ZIP container rules,
container rootfile, package metadata, unique manifest IDs, manifest resources,
spine references, navigation document, XML/XHTML parsing, XHTML namespaces,
local image references, and publication identifier. The full-corpus validator
opens and checks every generated book, including the shortest, longest,
illustrated, and ruby-heaviest corpus members.

The package deliberately contains both EPUB 3 navigation and NCX, uses only
portable XHTML/CSS, and embeds every runtime image. This provides a broad
compatibility baseline for current EPUB 3 readers and older readers that still
depend on NCX. The repository does not bundle Java, so official EPUBCheck is
not executed locally; it can be added as a second release validator without
changing the generated format.
