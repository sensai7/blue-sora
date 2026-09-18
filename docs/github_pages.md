# GitHub Pages deployment

Blue Sora's deployed application consists only of HTML, CSS, JavaScript, JSON,
images, and later download artifacts. GitHub Pages serves these files; it does
not run the Python generators.

## URL model

All generated internal URLs are relative to the site artifact. Root pages use
paths such as `works/<slug>/index.html` and `assets/<fingerprint>.css`; work
pages use `../../assets/` and `../../media/`. This allows one artifact to run
unchanged at a GitHub project subpath, a user site, or a custom domain.

The explicit `index.html` suffix also makes navigation unambiguous in static
hosting and when inspecting generated files locally. Catalog search and filters
load the fingerprinted JSON index in the browser. Work selection navigates to
the corresponding pre-generated HTML document.

## Publishing workflow

Corpus inputs and intermediate build products are intentionally ignored. The
deployable `build/site` artifact is versioned so GitHub Actions does not need
access to the external source corpus.

1. Run `scripts/build_site.py` locally after source or catalog changes.
2. Run `scripts/validate_site.py` and the test suite.
3. Commit the source changes and `build/site` together.
4. Push to `main`.
5. In the repository, select **Settings → Pages → GitHub Actions** as the
   publishing source if it is not already selected.

`.github/workflows/pages.yml` validates the committed artifact, uploads it as a
Pages artifact, and deploys it to the `github-pages` environment. The generated
`.nojekyll` marker also prevents accidental Jekyll interpretation when the
artifact is served through another branch-based static workflow.

## Local preview

The application has no server-side runtime. A small local HTTP server is still
useful because browsers apply stricter security rules to `file://` JSON fetches:

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --directory build\site
```

That command only serves static files and does not provide application logic.
