"""
VarraTek Security — Semi-automated blog publishing system.
Generates SEO-optimized cybersecurity articles via OpenAI, saves as drafts,
and publishes to GitHub on approval.
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
BLOG_DIR = SCRIPT_DIR / "blog"
DRAFTS_DIR = BLOG_DIR / "drafts"
PUBLISHED_DIR = BLOG_DIR / "published"
TEMPLATE_PATH = SCRIPT_DIR / "blog_template.html"
SITEMAP_PATH = SCRIPT_DIR / "sitemap.xml"

# Base URL for sitemap (e.g. https://winrush.github.io/VarraTek)
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://winrush.github.io/VarraTek").rstrip("/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Generate SEO-friendly filename from title."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug[:80].strip("-") or "post"


def ensure_dirs() -> None:
    """Create blog directories if they don't exist."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)


def load_template() -> str:
    """Load blog HTML template."""
    if not TEMPLATE_PATH.exists():
        sys.exit(f"Template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# OpenAI generation
# ---------------------------------------------------------------------------

def get_openai_client():
    """Return OpenAI client; exit if key missing or import fails."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY environment variable is not set.")
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except ImportError:
        sys.exit("OpenAI package required. Run: pip install openai")


def generate_blog_content(topic: str) -> dict:
    """
    Call OpenAI to generate title, meta, keywords, and article body.
    Returns dict with keys: title, meta_description, keywords, content.
    """
    client = get_openai_client()

    system = """You are an expert cybersecurity content writer for VarraTek Security, an enterprise cybersecurity and IT consulting firm. Write in a professional, authoritative tone. Output exactly in this format — do not add extra text before or after:

SEO_TITLE: [One line, max 60 characters, no quotes]
META_DESCRIPTION: [One line, max 160 characters, no quotes]
KEYWORDS: [Exactly 5 comma-separated keywords, no quotes]
---
[Article body as clean HTML only: use <h1> for the main title, <h2> for major sections, <h3> for subsections, <p> for paragraphs, <ul>/<li> or <ol>/<li> where appropriate. No <html>, <head>, or <body>. Approximately 1000 words. Do NOT include a CTA or "contact us" block — that is added by the template.]"""

    user = f"Write a comprehensive, SEO-optimized cybersecurity blog post on this topic: {topic}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
        )
    except Exception as e:
        sys.exit(f"OpenAI API error: {e}")

    raw = response.choices[0].message.content or ""
    return parse_generated_content(raw)


def parse_generated_content(raw: str) -> dict:
    """Parse model output into title, meta_description, keywords, content."""
    # Normalize line endings
    raw = raw.replace("\r\n", "\n").strip()

    if "---" not in raw:
        sys.exit("Generated content missing required '---' separator.")

    front, _, content = raw.partition("---")
    content = content.strip()

    title = ""
    meta_description = ""
    keywords = ""

    for line in front.split("\n"):
        line = line.strip()
        if line.startswith("SEO_TITLE:"):
            title = line.replace("SEO_TITLE:", "").strip()[:60]
        elif line.startswith("META_DESCRIPTION:"):
            meta_description = line.replace("META_DESCRIPTION:", "").strip()[:160]
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()

    if not title:
        title = "Cybersecurity Article"
    if not meta_description:
        meta_description = "Cybersecurity insights from VarraTek Security."
    if not keywords:
        keywords = "cybersecurity, security, enterprise, compliance, risk"

    return {
        "title": title,
        "meta_description": meta_description,
        "keywords": keywords,
        "content": content or "<p>Content could not be generated.</p>",
    }


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------

def render_html(data: dict) -> str:
    """Fill template with generated data."""
    template = load_template()
    return (
        template.replace("{{title}}", escape_html(data["title"]))
        .replace("{{meta_description}}", escape_html(data["meta_description"]))
        .replace("{{keywords}}", escape_html(data["keywords"]))
        .replace("{{content}}", data["content"])
    )


def escape_html(s: str) -> str:
    """Escape for use in HTML attributes/text."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def save_draft(slug: str, html: str) -> Path:
    """Save HTML to blog/drafts/{slug}.html. Returns path."""
    ensure_dirs()
    path = DRAFTS_DIR / f"{slug}.html"
    path.write_text(html, encoding="utf-8")
    return path


def move_to_published(slug: str) -> Path:
    """Move draft to published. Returns path of published file."""
    src = DRAFTS_DIR / f"{slug}.html"
    if not src.exists():
        sys.exit(f"Draft not found: {src}")
    dest = PUBLISHED_DIR / f"{slug}.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    src.unlink()
    return dest


def write_published_html(slug: str, html: str) -> Path:
    """Write HTML directly to published (for existing-draft publish). Returns path."""
    ensure_dirs()
    dest = PUBLISHED_DIR / f"{slug}.html"
    dest.write_text(html, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def ensure_sitemap_exists() -> None:
    """Create sitemap.xml with root structure if missing."""
    if SITEMAP_PATH.exists():
        return
    SITEMAP_PATH.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "</urlset>\n",
        encoding="utf-8",
    )


def add_url_to_sitemap(url_path: str, lastmod: str) -> None:
    """Append a <url> entry to sitemap.xml."""
    ensure_sitemap_exists()
    text = SITEMAP_PATH.read_text(encoding="utf-8")
    entry = (
        f'  <url>\n'
        f'    <loc>{url_path}</loc>\n'
        f'    <lastmod>{lastmod}</lastmod>\n'
        f'  </url>\n'
    )
    if "</urlset>" in text:
        text = text.replace("</urlset>", entry + "</urlset>")
    else:
        text = text.rstrip() + "\n" + entry + "</urlset>\n"
    SITEMAP_PATH.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def git_add_commit_push(commit_message: str) -> bool:
    """Run git add ., git commit, git push. Returns True on success."""
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=True,
            shell=os.name == "nt",
        )
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=True,
            shell=os.name == "nt",
        )
        subprocess.run(
            ["git", "push"],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=True,
            shell=os.name == "nt",
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e.stderr.decode() if e.stderr else e}")
        return False


# ---------------------------------------------------------------------------
# Publish existing draft (e.g. .md or pre-made content)
# ---------------------------------------------------------------------------

def parse_md_draft(path: Path) -> dict:
    """
    Parse a markdown draft with SEO Metadata block at top.
    Returns dict with title, meta_description, keywords, content (HTML).
    """
    text = path.read_text(encoding="utf-8")
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        sys.exit("Draft must contain exactly one '---' separating metadata from body.")

    meta_block, body_md = parts[0].strip(), parts[1].strip()

    # Extract title: line immediately after "**SEO Title" or "SEO Title...:**"
    title = ""
    title_match = re.search(r"(?:\*\*SEO Title[^*]*\*\*|SEO Title[^\n]*:)\s*\n\s*([^\n]+)", meta_block, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()[:60]

    # Extract meta description: line after "**Meta Description" or "Meta Description...:**"
    meta_description = ""
    meta_match = re.search(r"(?:\*\*Meta Description[^*]*\*\*|Meta Description[^\n]*:)\s*\n\s*([^\n]+)", meta_block, re.IGNORECASE)
    if meta_match:
        meta_description = meta_match.group(1).strip()[:160]

    # Keywords: lines like "1. keyword" (take first 5)
    keywords_list = re.findall(r"^\d+\.\s+(.+)$", meta_block, re.MULTILINE)
    keywords_list = [k.strip() for k in keywords_list[:5] if k.strip()]

    if not title:
        first_h1 = re.search(r"^#\s+(.+)$", body_md, re.MULTILINE)
        title = first_h1.group(1).strip()[:60] if first_h1 else "Blog Post"
    if not meta_description:
        meta_description = "Cybersecurity insights from VarraTek Security."
    keywords = ", ".join(keywords_list) if keywords_list else "cybersecurity, security, enterprise, compliance, risk"

    try:
        import markdown
        content_html = markdown.markdown(body_md, extensions=["extra", "nl2br"])
    except ImportError:
        sys.exit("Markdown package required for .md drafts. Run: pip install markdown")
    except Exception as e:
        sys.exit(f"Markdown conversion failed: {e}")

    return {
        "title": title,
        "meta_description": meta_description,
        "keywords": keywords,
        "content": content_html,
    }


def publish_existing(path_str: str) -> None:
    """Publish an existing draft file (.md or .html). Updates sitemap and pushes to git."""
    path = Path(path_str).resolve()
    if not path.exists():
        sys.exit(f"File not found: {path}")

    if path.suffix.lower() == ".md":
        data = parse_md_draft(path)
        slug = slugify(data["title"])
        html = render_html(data)
        write_published_html(slug, html)
        title = data["title"]
    elif path.suffix.lower() == ".html":
        html = path.read_text(encoding="utf-8")
        title_match = re.search(r"<title>(.+?) — VarraTek Security</title>", html)
        title = title_match.group(1).strip() if title_match else path.stem
        slug = slugify(title)
        dest = PUBLISHED_DIR / f"{slug}.html"
        ensure_dirs()
        dest.write_text(html, encoding="utf-8")
    else:
        sys.exit("Only .md and .html drafts are supported.")

    url = f"{SITE_BASE_URL}/blog/published/{slug}.html"
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    add_url_to_sitemap(url, lastmod)
    commit_message = f"New blog post: {title}"
    if not git_add_commit_push(commit_message):
        print("Published locally. Git push failed — run 'git push' manually.")
    else:
        print("Published and pushed to GitHub.")
    print(f"URL: {url}")


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def create_draft(topic: str) -> tuple[Path, str]:
    """Generate article from topic, save as draft. Returns (path, slug)."""
    print("Generating article...")
    data = generate_blog_content(topic)
    slug = slugify(data["title"])
    html = render_html(data)
    path = save_draft(slug, html)
    print(f"Draft saved: {path}")
    return path, slug


def publish_draft(slug: str, title: str) -> bool:
    """Move draft to published, update sitemap, git commit and push."""
    move_to_published(slug)
    url = f"{SITE_BASE_URL}/blog/published/{slug}.html"
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    add_url_to_sitemap(url, lastmod)
    commit_message = f"New blog post: {title}"
    if not git_add_commit_push(commit_message):
        print("Publish completed locally; git push failed. Run git push manually.")
        return False
    print("Published and pushed to GitHub.")
    return True


def main() -> None:
    ensure_dirs()

    if len(sys.argv) >= 3 and sys.argv[1].lower() == "--publish":
        publish_existing(sys.argv[2])
        return

    topic = input("Enter blog topic: ").strip()
    if not topic:
        sys.exit("Topic is required.")

    draft_path, slug = create_draft(topic)

    while True:
        answer = input("Publish this article? (yes/no): ").strip().lower()
        if answer in ("no", "n"):
            print("Draft left in blog/drafts. Edit and run again to publish later.")
            break
        if answer in ("yes", "y"):
            # Get title from draft for commit message (before move)
            html = draft_path.read_text(encoding="utf-8")
            title_match = re.search(r"<title>(.+?) — VarraTek Security</title>", html)
            title = title_match.group(1).strip() if title_match else slug
            publish_draft(slug, title)
            break
        print("Please answer yes or no.")


if __name__ == "__main__":
    main()
