# Online reader

Milestone 7 generates one self-contained work page under
`build/site/works/<stable-slug>/` for every reduced-corpus record.

## Content rendering

Canonical blocks are rendered without source stylesheets. Source heading levels
remain `h2` through `h4`; deterministic section anchors power the table of
contents. Ruby, emphasis, warichu, notes, small text, subscript, superscript,
source anchors, lists, tables, illustrations, and gaiji retain semantic HTML.

Stored source assets are copied to `build/site/media/` using their content IDs.
Reader pages never depend on remote images. A missing local asset becomes a
labelled inline fallback rather than an empty or broken image.

## Reading state

The browser stores a per-work scroll ratio locally and restores it on a later
visit unless the URL contains an explicit anchor. Reading progress is exposed
as an accessible progress bar. Text size controls persist one global reader
preference and degrade safely when browser storage is unavailable.

## Export states

Each EPUB and PDF control has one of three states:

- `available`: a local artifact exists under `build/site/downloads/` and the
  control is a download link.
- `unavailable`: the corresponding export milestone has not produced an
  artifact; the disabled control names that dependency.
- `error`: a sibling `.error.txt` marker exists and the disabled control exposes
  an alert state.

M7 intentionally does not fabricate EPUB or PDF files. M8 and M9 can populate
the download directory without changing the work-page contract.
