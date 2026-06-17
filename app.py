"""
LinkedIn Generator — SuperOffice Blog
Streamlit webapp: henter artikler, genererer LinkedIn-kladder
Deploy gratis på https://streamlit.io/cloud
"""
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
import streamlit as st
from bs4 import BeautifulSoup

# ─── Konstanter ───────────────────────────────────────────────────────────────

BLOG_URL      = "https://www.superoffice.com/blog/"
MAX_ARTICLES  = 20
MAX_BODY_CHARS = 6000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

SYSTEM_PROMPT = """Du er Johannes Jennebo — Consulting Director for SuperOffice i Norden.
Du skriver LinkedIn-opslag baseret på SuperOffice-blogartikler.

Din stil:
- Direkte og professionel, men personlig og varm
- Starter altid med en konkret observation eller situation — ALDRIG en generisk indledning
- Skriv på dansk
- 5-8 afsnit, maks 1-2 sætninger pr. afsnit
- Brug din nordiske erfaring: nævn kunder, møder, konkrete eksempler fra praksis
- Slut ALTID med et åbent spørgsmål til læseren
- INGEN hashtags
- INGEN emojis (undtagen ét 👇 allersidst)
- Nævn ikke "blog" eller "artikel" — skriv som om det er din egen indsigt"""

CATEGORY_COLORS = {
    "AI": "#6366f1",
    "Sales": "#10b981",
    "Service": "#f59e0b",
    "Data": "#ef4444",
    "Integration": "#3b82f6",
    "Marketing": "#ec4899",
    "CRM": "#8b5cf6",
}


# ─── Scraping ─────────────────────────────────────────────────────────────────

def fetch_html(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception:
            if i < retries - 1:
                time.sleep(2)
    return None


def parse_date(raw):
    if not raw:
        return datetime.today().strftime("%Y-%m-%d")
    raw = raw.strip().rstrip(",")
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%d/%m/%Y", "%d %B %Y"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.today().strftime("%Y-%m-%d")


def guess_cat(title):
    t = title.lower()
    if any(w in t for w in ["ai ", "artificial intelligence", "machine learning", "copilot", "chatgpt"]):
        return "AI"
    if any(w in t for w in ["pipeline", "forecast", "quota", "revenue", "deal", "sales process"]):
        return "Sales"
    if any(w in t for w in ["customer service", "support", "complaint", "helpdesk"]):
        return "Service"
    if any(w in t for w in ["data quality", "duplicate", "dirty data", "data silo"]):
        return "Data"
    if any(w in t for w in ["erp", "integration", "api", "microsoft 365", "connect", "sync"]):
        return "Integration"
    if any(w in t for w in ["email", "marketing", "campaign", "lead generation"]):
        return "Marketing"
    return "CRM"


def get_article_links(html):
    soup = BeautifulSoup(html, "html.parser")
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^/blog/[a-z0-9][a-z0-9\-]{4,}/$", href):
            full = urljoin(BLOG_URL, href)
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links[:MAX_ARTICLES]


def fetch_article(url):
    html = fetch_html(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            title = re.sub(r"\s*[-|]\s*(SuperOffice|Blog).*$", "", t.get_text(strip=True), flags=re.I).strip()
    if not title or len(title) < 5:
        return None

    date_str = ""
    time_el = soup.find("time")
    if time_el:
        date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)

    for tag in soup.select(
        "nav,header,footer,aside,script,style,noscript,"
        "[class*='sidebar'],[class*='related'],[class*='share'],"
        "[class*='newsletter'],[class*='cta'],[class*='cookie']"
    ):
        tag.decompose()

    body = None
    for sel in ["[class*='wysiwyg']", "[class*='content__main']", "[class*='article']", "main"]:
        body = soup.select_one(sel)
        if body and len(body.get_text(strip=True)) > 200:
            break
    if not body:
        body = soup.find("body")

    parts = []
    if body:
        for el in body.find_all(["p", "h2", "h3", "h4", "li"]):
            t = el.get_text(strip=True)
            if t and len(t) > 25:
                parts.append(t)

    full_text = "\n\n".join(parts)
    if len(full_text) > MAX_BODY_CHARS:
        full_text = full_text[:MAX_BODY_CHARS] + "\n\n[afkortet]"

    return {
        "titleEn": title,
        "date":    parse_date(date_str),
        "summary": parts[0][:300] if parts else "",
        "fullText": full_text,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def load_articles():
    html = fetch_html(BLOG_URL)
    if not html:
        return []
    links = get_article_links(html)
    articles = []
    for url in links:
        data = fetch_article(url)
        if not data:
            continue
        articles.append({
            "titleEn":  data["titleEn"],
            "category": guess_cat(data["titleEn"]),
            "date":     data["date"],
            "summary":  data["summary"],
            "fullText": data["fullText"],
            "url":      url,
        })
        time.sleep(0.5)
    return articles


# ─── Hjælpefunktioner ─────────────────────────────────────────────────────────

def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def make_prompt(article):
    return f"""Du er Johannes Jennebo — Consulting Director for SuperOffice i Norden.

Skriv et LinkedIn-opslag på DANSK baseret på denne artikel.

Titel: {article['titleEn']}
Resumé: {article['summary']}

Stil:
- Start med en konkret situation eller observation — aldrig en generisk indledning
- 5-8 korte afsnit (1-2 sætninger pr. afsnit)
- Nordisk perspektiv, personlig og professionel stemme
- Slut med et åbent spørgsmål til læserne
- INGEN hashtags, INGEN emojis (undtagen 👇 sidst)
- Skriv ikke "blogindlæg" eller "artikel"

Fuld artikeltekst:
{article.get('fullText', '')[:4000]}"""


def post_to_md(article, text):
    slug = article["url"].rstrip("/").split("/")[-1][:50]
    return (
        f"# {article['titleEn']}\n\n"
        f"**Kilde:** {article['url']}\n"
        f"**Dato:** {article['date']}\n"
        f"**Status:** Kladde\n\n---\n\n{text}\n"
    ), f"{article['date']}_{slug}.md"


# ─── Side-config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="LinkedIn Generator — SuperOffice",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stButton > button { border-radius: 6px; }
  .article-card { padding: 8px 10px; border-radius: 6px; margin-bottom: 4px;
                  border: 1px solid #e5e7eb; cursor: pointer; }
  .article-card:hover { background: #f9fafb; }
  div[data-testid="stSidebar"] { min-width: 340px; }
</style>
""", unsafe_allow_html=True)


# ─── Sidebar: artikelliste ─────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## SuperOffice Blog")

    refresh = st.button("Hent nye artikler", use_container_width=True)
    if refresh:
        st.cache_data.clear()

    with st.spinner("Henter artikler..."):
        articles = load_articles()

    if not articles:
        st.error("Kunne ikke hente artikler. Tjek din internetforbindelse.")
        st.stop()

    cats = sorted({a["category"] for a in articles})
    selected_cat = st.selectbox("Kategori", ["Alle"] + cats, label_visibility="collapsed")

    filtered = articles if selected_cat == "Alle" else [a for a in articles if a["category"] == selected_cat]
    st.caption(f"{len(filtered)} artikler")
    st.divider()

    for i, a in enumerate(filtered):
        label = f"{a['date'][:7]}  ·  **{a['titleEn'][:48]}**{'…' if len(a['titleEn']) > 48 else ''}"
        if st.button(label, key=f"a{i}", use_container_width=True):
            st.session_state["article"] = a
            st.session_state.pop("generated", None)


# ─── Hovedområde ──────────────────────────────────────────────────────────────

article = st.session_state.get("article")

if article is None:
    st.markdown("### Vælg en artikel til venstre")
    st.markdown(
        "Applikationen henter de seneste artikler fra SuperOffice-bloggen "
        "og hjælper dig med at skrive LinkedIn-opslag i din stemme."
    )
    st.stop()

# Artikelheader
col_title, col_meta = st.columns([3, 1])
with col_title:
    st.subheader(article["titleEn"])
with col_meta:
    cat   = article["category"]
    color = CATEGORY_COLORS.get(cat, "#6b7280")
    st.markdown(f'<span style="background:{color};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px">{cat}</span>&nbsp;&nbsp;`{article["date"]}`', unsafe_allow_html=True)

st.markdown(f"[Åbn original artikel]({article['url']})")
st.markdown(f"*{article['summary']}*")

st.divider()

# Genereringssktion
st.markdown("### LinkedIn-opslag")

has_key = bool(api_key())

if has_key:
    # ── API-tilstand: automatisk generering ──────────────────────────────────
    if st.button("Generer automatisk", type="primary"):
        with st.spinner("Genererer med Claude..."):
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key())
                msg = client.messages.create(
                    model="claude-opus-4-8",
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": make_prompt(article)}],
                )
                st.session_state["generated"] = msg.content[0].text.strip()
            except Exception as exc:
                st.error(f"Fejl: {exc}")
else:
    # ── Manuel tilstand: copy-paste til claude.ai ─────────────────────────────
    st.info(
        "Manuel tilstand — brug din gratis claude.ai-konto. "
        "Kopiér prompten nedenfor, indsæt den på claude.ai, "
        "og kom tilbage og indsæt svaret."
    )

    with st.expander("Vis prompt (klik for at kopiere)", expanded=True):
        prompt_text = make_prompt(article)
        st.code(prompt_text, language=None)

    st.link_button("Åbn claude.ai i ny fane", "https://claude.ai", use_container_width=True)

    st.markdown("**Indsæt svaret fra Claude her:**")
    manual = st.text_area("", height=280, placeholder="Paste LinkedIn-tekst her...", key="manual_paste")
    if st.button("Brug denne tekst", type="primary") and manual.strip():
        st.session_state["generated"] = manual.strip()


# ── Vis og gem kladde ─────────────────────────────────────────────────────────

if "generated" in st.session_state:
    st.divider()
    st.markdown("### Kladde")

    edited = st.text_area(
        "Redigér inden du poster:",
        value=st.session_state["generated"],
        height=400,
        key="editor",
    )

    md_content, filename = post_to_md(article, edited)

    col_dl, col_copy = st.columns(2)
    with col_dl:
        st.download_button(
            label="Download som .md",
            data=md_content.encode("utf-8"),
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
        )
    with col_copy:
        st.button("Kopiér tekst", on_click=lambda: None, use_container_width=True,
                  help="Marker teksten i feltet ovenfor og brug Ctrl/Cmd+C")

    st.caption(f"Gem filen i  projects/so-blog-agent/posts/{filename}")
