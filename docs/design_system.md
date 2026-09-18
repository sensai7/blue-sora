# Static site and design system

Milestone 5 uses Jinja 3.1 templates and a deterministic Python build. Source
templates live in `templates`, authored CSS/JavaScript in `site_assets`, and
generated output in `build/site`.

## Design foundation

- A restrained paper, ink, sky-blue, and seal-red palette with WCAG AA core
  foreground/background contrast.
- English UI uses a system sans stack; literary headings and Japanese prose
  use Georgia, Yu Mincho, Hiragino Mincho, Noto Serif JP, then generic serif.
- Fluid type and spacing tokens preserve vertical rhythm from phone to wide
  desktop displays.
- Breakpoints at 42rem and 64rem cover phone, tablet, and desktop layouts.
- Ruby annotations use centered alignment and a legible sans reading face.
- Focus indicators, a skip link, reduced-motion handling, landmarks, and
  accessible names are part of the shared shell.
- Missing covers use the reusable black `.book-cover--empty` component.

## Assets and browser baseline

CSS and JavaScript are local and content-fingerprinted. No remote font, script,
style, or image is required at runtime. The baseline is the current and prior
major versions of Chromium, Firefox, and Safari. Unsupported enhancements such
as backdrop blur degrade to the declared opaque background.

Run `scripts/validate_site.py` after building. It checks HTML structure,
accessibility basics, local fingerprinted asset references, output hashes,
responsive/reduced-motion rules, cover placeholders, and core contrast pairs.
