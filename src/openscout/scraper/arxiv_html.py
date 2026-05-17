"""arXiv HTML scraper — replaces PDF for email extraction.

arXiv now renders papers as HTML at https://arxiv.org/html/<id> (their own
native renderer; older papers fall back to ar5iv.labs.arxiv.org). This is
**much lighter** than PDF parsing:

  PDF:  500KB – 2MB · pypdf, slow + brittle on math-heavy docs
  HTML: 50 – 200KB · selectolax, milliseconds, structured DOM

We extract:
  - All emails on the first ~6000 chars (author block lives near the top)
  - Author affiliation strings (h2/h3 sections)
  - GitHub URLs (sometimes in the abstract that PDF misses)

Affiliation extraction is intentionally conservative: when a paper has
multiple affiliations and we cannot unambiguously pin each author to one,
we record the raw strings via a `Signal(type="arxiv_affiliations")` row
and DO NOT touch `Researcher.current_affiliation_id`. Wrong affiliation
is worse than no affiliation.

Falls back to ar5iv.labs.arxiv.org/abs/<id> when arxiv.org/html/<id> 404s.
"""

import re
import time

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy import desc, select

from ..db import session_scope
from ..models import Institution, Paper, PaperAuthor, Researcher, Signal

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.UNICODE,
)
GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[\w.\-]+/[\w.\-]+",
    re.IGNORECASE,
)

# Heuristic: substrings that strongly suggest a string is an institution.
# Hits are matched case-insensitively. List is conservative; false positives
# are far costlier than misses here.
_INSTITUTION_HINTS = (
    "university",
    "universität",
    "université",
    "universidad",
    "institute",
    "institut ",
    "school of",
    "college",
    "laboratory",
    "labs",
    " lab",
    "research",
    "academia",
    "academy",
    "csail",
    "deepmind",
    "openai",
    "anthropic",
    "google",
    "microsoft",
    "meta ai",
    "facebook ai",
    "nvidia",
    "amazon",
    "apple",
    "huawei",
    "alibaba",
    "baidu",
    "bytedance",
    "tencent",
    "ibm ",
    "salesforce",
    "tsinghua",
    "peking",
    "zhejiang",
    "shanghai",
    "fudan",
    "nankai",
    "renmin",
    "stanford",
    "berkeley",
    "harvard",
    " mit",
    "mit ",
    "cmu",
    "caltech",
    "ethz",
    "eth zurich",
    "epfl",
    "oxford",
    "cambridge",
    "imperial",
    "tokyo",
    "kyoto",
    "kaist",
    "seoul",
    "national",
    "polytechn",
    "tech ",
    "centre",
    "center",
    "department",
    "faculty",
    "corp",
    " inc",
    " ltd",
    "gmbh",
    "ai lab",
)

# Lines containing these tokens are almost certainly NOT institution names.
_NEGATIVE_HINTS = (
    "@",
    "http://",
    "https://",
    "corresponding author",
    "co-first author",
    "equal contribution",
    "equally contributed",
)

# Leading superscript-style affiliation marker. arXiv HTML renders these as
# things like "1OpenGVLab, Shanghai AI Laboratory" once the <sup> is text-
# extracted. We tolerate up to 3 digits and optional trailing punctuation.
_SUP_LABEL_RE = re.compile(r"^\s*(\d{1,3})[\s,.:)]*")

# Strip dagger / asterisk / etc. marks that sometimes lead an affiliation line.
_LEAD_MARK_RE = re.compile(r"^[†‡\*†‡§¶#]+\s*")

# Junk arXiv sometimes injects when LaTeXML can't expand a macro.
_BAD_PLACEHOLDERS = ("[1]", "[2]", "[3]", "[4]", "[5]", "[6]")

HEADERS = {
    "User-Agent": "OpenScout/0.7 (+https://github.com/Chen17-sq/OpenScout)",
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch_html(client: httpx.Client, arxiv_id: str) -> str | None:
    """Try arXiv native HTML first, then ar5iv mirror."""
    for url in (
        f"https://arxiv.org/html/{arxiv_id}v1",
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ):
        try:
            r = client.get(url, timeout=20.0, follow_redirects=True)
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                return r.text
        except Exception:
            continue
    return None


def _clean_emails(matches: list[str]) -> list[str]:
    out: set[str] = set()
    for raw in matches:
        e = raw.rstrip(".,;:)").lower()
        if e.endswith(".png") or e.endswith(".pdf") or e.endswith(".jpg"):
            continue
        if "..." in e:
            continue
        if e in {"example@example.com", "info@example.com", "noreply@arxiv.org"}:
            continue
        out.add(e)
    return sorted(out)


def _looks_like_affiliation(line: str) -> bool:
    """Cheap classifier: does this line look like an institution string?

    Conservative — false positives are far costlier than false negatives.
    """
    s = line.strip()
    if not s or len(s) < 4 or len(s) > 250:
        return False
    low = s.lower()
    if any(neg in low for neg in _NEGATIVE_HINTS):
        return False
    if s in _BAD_PLACEHOLDERS:
        return False
    # Pure-name lines: too many commas (>3) or short non-keyword tokens are
    # rejected unless they contain an institution hint.
    return any(hint in low for hint in _INSTITUTION_HINTS)


def _clean_affiliation_line(line: str) -> str:
    """Normalize whitespace, strip leading sup-digit and lead marks."""
    s = line.replace("\xa0", " ").strip()
    s = _LEAD_MARK_RE.sub("", s)
    # Strip a leading sup-digit label (e.g. "1OpenGVLab" → "OpenGVLab").
    s = _SUP_LABEL_RE.sub("", s)
    # Collapse internal whitespace runs (newlines, tabs, repeated spaces).
    s = re.sub(r"\s+", " ", s).strip()
    # Drop dangling trailing punctuation that line-splits commonly leave behind.
    s = s.rstrip(",;:.· \t-")
    return s


def _extract_affiliations(authors_node) -> list[str]:
    """Pull institution-shaped strings from the .ltx_authors block.

    Returns an ordered, deduped list. Tolerates arXiv's quirks:
      - Affiliations live mixed inside .ltx_personname after names
      - Some renders use .ltx_role_affiliation / .ltx_author_notes
      - LaTeXML failures produce "[1]" placeholders → skipped
    """
    if authors_node is None:
        return []

    # Gather candidate lines from every plausible sub-element + the raw text.
    raw_lines: list[str] = []

    # 1) Structured nodes if present.
    for selector in (".ltx_role_affiliation", ".ltx_author_notes"):
        for node in authors_node.css(selector):
            txt = node.text(separator="\n") or ""
            raw_lines.extend(txt.splitlines())

    # 2) Fallback / supplement: the whole author block text, split by newlines.
    #    LaTeXML renders <br class="ltx_break"> as newlines via text(),
    #    which is exactly the boundary we want between affiliation entries.
    full_text = authors_node.text(separator="\n") or ""
    raw_lines.extend(full_text.splitlines())

    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_lines:
        cleaned = _clean_affiliation_line(raw)
        if not cleaned:
            continue
        if cleaned in _BAD_PLACEHOLDERS:
            continue
        if not _looks_like_affiliation(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)

    return out


def _extract_from_html(html: str) -> tuple[list[str], str | None, list[str]]:
    """Parse first-page-ish region for emails + github url + affiliations."""
    if not html:
        return [], None, []

    # Use selectolax for speed; the first .ltx_authors block (or first 6000 chars
    # of body text) is enough for the author footer.
    tree = HTMLParser(html)

    # Try selectolax author-area extraction first
    candidate_text_parts: list[str] = []
    for selector in (".ltx_authors", ".ltx_personname", "header", "div.author"):
        for node in tree.css(selector)[:3]:
            candidate_text_parts.append(node.text() or "")

    # Fallback: first big chunk of plaintext
    if not candidate_text_parts:
        full = tree.body.text(separator=" ") if tree.body else ""
        candidate_text_parts = [full[:8000]]

    blob = " ".join(candidate_text_parts)
    raw_emails = EMAIL_RE.findall(blob)
    emails = _clean_emails(raw_emails)

    # GitHub url — search broader body too
    full_text = tree.body.text(separator=" ") if tree.body else blob
    gh = None
    for m in GITHUB_RE.finditer(full_text):
        url = m.group(0).rstrip(".,);:")
        if "github.com/static" in url or "github.com/topics" in url:
            continue
        gh = url
        break

    # Affiliations — only from the FIRST .ltx_authors block. Multiple blocks
    # would belong to e.g. responses or appendices and aren't safe to mix.
    affiliations = _extract_affiliations(tree.css_first(".ltx_authors"))

    return emails, gh, affiliations


# ── institution matching + per-researcher assignment ─────────────────────────


# Reused trim heuristic from affiliation_discovery._normalize, kept local to
# avoid coupling the two modules — we only need a lightweight match here.
_PREFIX_RE = re.compile(r"^(the\s+|university\s+of\s+)", re.IGNORECASE)


def _norm_inst(name: str) -> str:
    s = (name or "").strip().lower()
    for _ in range(2):
        s = _PREFIX_RE.sub("", s).strip()
    s = re.sub(r"[\s\-_,.;:()/]+", " ", s).strip()
    return s


def _match_institution(db, raw: str) -> Institution | None:
    """Match a raw affiliation string to an existing Institution row.

    Strategy (in order, stop at first hit):
      1. Exact (normalized) name match
      2. Substring: institution name normalized appears in the raw, OR vice-
         versa, AND the candidate name is >= 6 chars (avoids matching "AI"
         or other short tokens that would explode into false positives).
    """
    if not raw or not raw.strip():
        return None
    target = _norm_inst(raw)
    if not target or len(target) < 4:
        return None

    # Pull a candidate set with a cheap LIKE on the first long-enough token.
    tokens = [t for t in target.split(" ") if len(t) >= 4]
    if not tokens:
        return None
    like = f"%{tokens[0]}%"
    candidates = list(
        db.execute(select(Institution).where(Institution.name.ilike(like))).scalars().all()
    )

    # 1) exact normalized match wins
    for inst in candidates:
        if _norm_inst(inst.name or "") == target:
            return inst
        if inst.name_zh and _norm_inst(inst.name_zh) == target:
            return inst

    # 2) bidirectional substring (only if both sides are long enough to be safe)
    for inst in candidates:
        n = _norm_inst(inst.name or "")
        if len(n) < 6:
            continue
        if n in target or target in n:
            return inst
    return None


def _try_assign_affiliations(db, paper: Paper, affiliations: list[str]) -> int:
    """Attempt to assign `current_affiliation_id` to this paper's researcher
    authors using the extracted affiliation strings. Returns count assigned.

    Conservative policy:
      - Only acts on researchers with NO current_affiliation_id.
      - Only assigns when the paper has EXACTLY ONE affiliation string that
        matches a known Institution. (Position-aligned multi-affil assignment
        is too brittle: arXiv's authors-vs-affiliations indexing is not
        machine-readable.)
    """
    if not affiliations:
        return 0
    # Per spec: single-affiliation paper → safe to assign to all unset authors.
    if len(affiliations) != 1:
        return 0

    inst = _match_institution(db, affiliations[0])
    if inst is None:
        return 0

    author_links = list(
        db.execute(select(PaperAuthor).where(PaperAuthor.paper_id == paper.id)).scalars().all()
    )
    if not author_links:
        return 0

    assigned = 0
    for link in author_links:
        r = db.get(Researcher, link.researcher_id)
        if r is None or r.current_affiliation_id is not None:
            continue
        r.current_affiliation_id = inst.id
        r.affiliation_source = "arxiv_html"
        assigned += 1
    return assigned


def _record_affiliations_signal(db, paper: Paper, affiliations: list[str]) -> None:
    """Attach a Signal row capturing the raw affiliation strings.

    Anchored on the paper's first author (by position). This is a record-
    keeping move — downstream affiliation resolvers can revisit these
    strings later with more context (e.g. once the Institution table grows).
    Idempotent: skips if a matching Signal already exists for this paper.
    """
    if not affiliations:
        return
    first_link = (
        db.execute(
            select(PaperAuthor)
            .where(PaperAuthor.paper_id == paper.id)
            .order_by(PaperAuthor.position.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if first_link is None:
        return
    source_key = f"paper:{paper.id}"
    existing = db.execute(
        select(Signal).where(
            Signal.researcher_id == first_link.researcher_id,
            Signal.type == "arxiv_affiliations",
            Signal.source == source_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Signal(
            researcher_id=first_link.researcher_id,
            type="arxiv_affiliations",
            payload={
                "paper_id": paper.id,
                "arxiv_id": paper.arxiv_id,
                "affiliations": affiliations,
            },
            source=source_key,
        )
    )


def scrape_papers(limit: int = 30, sleep_between: float = 1.2) -> dict[str, int]:
    """Walk papers with arxiv_id but no author_emails / code_url; fill both,
    plus extract author affiliation strings and (conservatively) assign them
    to researcher authors.
    """
    counts = {
        "attempted": 0,
        "with_emails": 0,
        "with_code": 0,
        "with_affiliations": 0,
        "affiliations_assigned": 0,
        "errors": 0,
        "no_html": 0,
    }

    client = httpx.Client(headers=HEADERS, follow_redirects=True)
    try:
        with session_scope() as db:
            papers = list(
                db.execute(
                    select(Paper)
                    .where(
                        Paper.arxiv_id.is_not(None),
                        Paper.arxiv_id.notlike("or-%"),  # skip OpenReview synthetic ids
                        Paper.author_emails.is_(None),
                    )
                    .order_by(desc(Paper.first_seen_at))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            for paper in papers:
                counts["attempted"] += 1
                html = _fetch_html(client, paper.arxiv_id)
                if not html:
                    counts["no_html"] += 1
                    paper.author_emails = []  # mark attempted
                    time.sleep(sleep_between)
                    continue
                try:
                    emails, gh, affiliations = _extract_from_html(html)
                except Exception:
                    counts["errors"] += 1
                    paper.author_emails = []
                    time.sleep(sleep_between)
                    continue
                paper.author_emails = emails
                if emails:
                    counts["with_emails"] += 1
                if gh and not paper.code_url:
                    paper.code_url = gh
                    counts["with_code"] += 1
                if affiliations:
                    counts["with_affiliations"] += 1
                    # Signal recording + per-researcher assignment are both
                    # best-effort. A DB hiccup here should not invalidate
                    # the email/code extraction we just successfully wrote.
                    try:
                        _record_affiliations_signal(db, paper, affiliations)
                    except Exception:
                        counts["errors"] += 1
                    try:
                        counts["affiliations_assigned"] += _try_assign_affiliations(
                            db, paper, affiliations
                        )
                    except Exception:
                        counts["errors"] += 1
                time.sleep(sleep_between)
    finally:
        client.close()
    return counts
