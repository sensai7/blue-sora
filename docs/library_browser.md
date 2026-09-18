# Library browser

The generated home page is a complete static catalog browser. It fetches one
fingerprinted, compact JSON index and performs search, filtering, sorting, and
pagination in the browser; no application server or database is required.

## URL state

All non-default state is represented by query parameters so a catalog view can
be bookmarked, shared, and restored with browser navigation:

| Parameter | Accepted values |
| --- | --- |
| `q` | Unicode title, title reading, Japanese author name/reading, or romanized author name |
| `difficulty` | `approachable`, `intermediate`, `advanced`, `unscored` |
| `length` | `short`, `medium`, `long` |
| `author` | Stable catalog author ID |
| `era` | `Meiji`, `Taisho`, `Showa` |
| `metadata` | `scored`, `illustrated`, `old-orthography` |
| `sort` | `title`, `author`, `length-asc`, `length-desc`, `difficulty-asc`, `difficulty-desc` |
| `page` | Positive integer; 24 works per page |

Unicode search uses NFKC normalization and Japanese-aware lowercasing. Era is
derived from the author's death year because this corpus does not contain an
original-publication date: through 1912 is Meiji, through 1926 is Taisho, and
later is Showa. The interface labels and exposes this as catalog metadata, not
as a claim about an individual work's exact publication era.

Unknown filter values are removed and announced. Out-of-range pages are
clamped to the nearest valid page. If the JSON index cannot load, the six-work
server-rendered preview remains visible with a clear error message.

## Scaling behavior

Only 24 cards are placed in the DOM at a time. The index excludes canonical
body text and retains only comparison and search fields, keeping transfer and
client-side processing proportional to catalog metadata rather than corpus
text size.
