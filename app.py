"""
SO Blog Agent — LinkedIn Post Generator
Streamlit webapp · deploy på streamlit.io/cloud

Gratis auto-generering: sæt GROQ_API_KEY i Streamlit Cloud secrets
Hent gratis nøgle: console.groq.com (kun email, ingen betalingskort)
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

BLOG_URL       = "https://www.superoffice.com/blog/"
MAX_ARTICLES   = 20
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

CAT_STYLE = {
    "AI":          ("#e0e7ff", "#4338ca"),
    "Sales":       ("#d1fae5", "#065f46"),
    "Service":     ("#fef3c7", "#92400e"),
    "Data":        ("#fee2e2", "#991b1b"),
    "Integration": ("#fde8d0", "#c2410c"),
    "Marketing":   ("#fce7f3", "#9d174d"),
    "CRM":         ("#ede9fe", "#5b21b6"),
}

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SO Blog Agent",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS — skjul Streamlit-chrome, sæt layout ─────────────────────────────────

st.markdown("""
<style>
  /* Skjul alle Streamlit UI-elementer */
  [data-testid="stHeader"]        { display: none !important; }
  [data-testid="stToolbar"]       { display: none !important; }
  [data-testid="stDecoration"]    { display: none !important; }
  [data-testid="stSidebar"]       { display: none !important; }
  [data-testid="collapsedControl"]{ display: none !important; }
  .stDeployButton                 { display: none !important; }
  #MainMenu, footer               { visibility: hidden !important; }

  /* App-baggrund og layout */
  .stApp { background: #f5f4f0 !important; }
  .block-container {
    padding: 2rem 2.5rem 4rem 2.5rem !important;
    max-width: 900px !important;
    margin: 0 auto !important;
  }

  /* Stat-kort */
  .stat-card {
    background: white; border: 1px solid #e5e7eb;
    border-radius: 12px; padding: 20px 22px;
  }
  .stat-label {
    font-size: 11px; color: #9ca3af; font-weight: 600;
    letter-spacing: .07em; text-transform: uppercase; margin-bottom: 6px;
  }
  .stat-value { font-size: 34px; font-weight: 700; color: #111827; line-height: 1.1; }

  /* Artikel-kort */
  .art-card {
    background: white; border: 1px solid #e5e7eb;
    border-radius: 12px; padding: 16px 20px 14px 20px;
  }
  .art-title { font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 3px; }
  .art-meta  { font-size: 12px; color: #9ca3af; margin-bottom: 10px; }

  /* Badges */
  .badge {
    display: inline-block; border-radius: 20px;
    font-size: 11px; font-weight: 500; padding: 2px 10px; margin-right: 4px;
  }
  .b-ny       { background: #fed7aa; color: #c2410c; }
  .b-kladde   { background: #f3f4f6; color: #374151; }
  .b-planlagt { background: #dbeafe; color: #1d4ed8; }
  .b-udgivet  { background: #d1fae5; color: #065f46; }

  /* "Generer post" knap */
  div[data-testid="stButton"] > button[kind="primary"] {
    background: #111827 !important; color: white !important;
    border: none !important; border-radius: 8px !important;
    font-size: 13px !important; font-weight: 500 !important;
    white-space: nowrap !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #374151 !important;
  }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] { background: transparent; gap: 8px; }
  .stTabs [data-baseweb="tab"] {
    background: transparent; border: none;
    font-size: 14px; color: #6b7280; padding: 8px 4px;
  }
  .stTabs [aria-selected="true"] {
    color: #111827 !important; font-weight: 600;
    border-bottom: 2px solid #111827 !important;
  }

  /* Radio filter-pills */
  div[data-testid="stRadio"] > div { gap: 6px; }
  div[data-testid="stRadio"] label {
    border: 1px solid #e5e7eb; border-radius: 20px;
    padding: 4px 14px; font-size: 13px; background: white; cursor: pointer;
  }
  div[data-testid="stRadio"] label:has(input:checked) {
    background: #111827; color: white; border-color: #111827;
  }

  /* Genereret post-boks */
  .post-box {
    background: white; border: 1px solid #e5e7eb;
    border-radius: 12px; padding: 20px 22px; margin-top: 4px;
    white-space: pre-wrap; font-size: 14px; line-height: 1.7; color: #111827;
  }
</style>
""", unsafe_allow_html=True)


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
    if any(w in t for w in ["ai ", "artificial intelligence", "machine learning", "copilot"]):
        return "AI"
    if any(w in t for w in ["pipeline", "forecast", "quota", "revenue", "deal", "sales"]):
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
            title = re.sub(r"\s*[-|]\s*(SuperOffice|Blog).*$", "",
                           t.get_text(strip=True), flags=re.I).strip()
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
        "titleEn":  title,
        "date":     parse_date(date_str),
        "summary":  parts[0][:300] if parts else "",
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
        time.sleep(0.4)
    return articles


# ─── Generering ───────────────────────────────────────────────────────────────

def make_prompt(article):
    return (
        f"Titel: {article['titleEn']}\n"
        f"Resumé: {article['summary']}\n\n"
        f"Fuld artikeltekst:\n{article.get('fullText', '')[:4000]}"
    )


def get_active_key():
    """Returnerer (provider, key) — groq foretrækkes (gratis), derefter anthropic."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        return "groq", groq_key
    anth_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anth_key:
        return "anthropic", anth_key
    return None, None


def generate_post(article):
    provider, key = get_active_key()

    if provider == "groq":
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": make_prompt(article)},
                ],
                "max_tokens": 1024,
                "temperature": 0.72,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip(), None

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": make_prompt(article)}],
        )
        return msg.content[0].text.strip(), None

    return None, "no_key"


# ─── Hjælpefunktioner ─────────────────────────────────────────────────────────

def art_state(url):
    return st.session_state.setdefault("states", {}).setdefault(
        url, {"status": "ny", "post": None}
    )


def set_art_state(url, status=None, post=None):
    s = art_state(url)
    if status is not None:
        s["status"] = status
    if post is not None:
        s["post"] = post


def cat_badge(cat):
    bg, fg = CAT_STYLE.get(cat, ("#f3f4f6", "#374151"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{cat}</span>'


def status_badge(status):
    cls = {"ny":"b-ny","kladde":"b-kladde","planlagt":"b-planlagt","udgivet":"b-udgivet"}.get(status,"b-kladde")
    return f'<span class="badge {cls}">{status.capitalize()}</span>'


def short_url(url):
    return url.replace("https://www.", "").replace("https://", "")[:55]


def post_to_md(article, text):
    slug = article["url"].rstrip("/").split("/")[-1][:50]
    content = (
        f"# {article['titleEn']}\n\n"
        f"**Kilde:** {article['url']}\n"
        f"**Dato:** {article['date']}\n"
        f"**Status:** Kladde\n\n---\n\n{text}\n"
    )
    return content, f"{article['date']}_{slug}.md"


# ─── HEADER ───────────────────────────────────────────────────────────────────

st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:28px;padding-top:4px">
  <div style="background:#0077B5;border-radius:12px;width:52px;height:52px;
              display:flex;align-items:center;justify-content:center;flex-shrink:0">
    <span style="color:white;font-weight:900;font-size:22px;font-family:Georgia,serif">in</span>
  </div>
  <div>
    <div style="font-size:22px;font-weight:700;color:#111827;line-height:1.2">SO Blog Agent</div>
    <div style="font-size:13px;color:#6b7280;margin-top:2px">Læser hele artiklen — skriver bedre posts</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── LOAD ARTIKLER ────────────────────────────────────────────────────────────

with st.spinner("Henter artikler fra superoffice.com/blog..."):
    articles = load_articles()

if not articles:
    st.error("Kunne ikke hente artikler. Tjek din internetforbindelse og prøv igen.")
    if st.button("Prøv igen"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

provider, _ = get_active_key()


# ─── STATS ROW ────────────────────────────────────────────────────────────────

states      = st.session_state.get("states", {})
planlagt_n  = sum(1 for a in articles if states.get(a["url"], {}).get("status") == "planlagt")
udgivet_n   = sum(1 for a in articles if states.get(a["url"], {}).get("status") == "udgivet")
full_text_n = sum(1 for a in articles if len(a.get("fullText", "")) > 200)

for col, label, val in zip(
    st.columns(4),
    ["ARTIKLER", "MED FULD TEKST", "PLANLAGT", "UDGIVET"],
    [len(articles), full_text_n, planlagt_n, udgivet_n],
):
    with col:
        st.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-label">{label}</div>'
            f'<div class="stat-value">{val}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='margin:20px 0 4px'></div>", unsafe_allow_html=True)

# Banner hvis ingen API-nøgle
if not provider:
    st.warning(
        "Ingen API-nøgle sat op — generering kræver en gratis Groq-nøgle. "
        "Gå til **console.groq.com** (kun email, intet betalingskort) og tilføj "
        "`GROQ_API_KEY` som secret i Streamlit Cloud.",
        icon="⚙️",
    )


# ─── TABS ─────────────────────────────────────────────────────────────────────

tab_kø, tab_kal, tab_sched = st.tabs(["Kø", "Kalender", "Scheduler"])

with tab_kal:
    st.info("Kalender-visning kommer snart.")

with tab_sched:
    st.info("Scheduler kommer snart.")

with tab_kø:

    # Filter pills
    fcol, scol = st.columns([4, 1])
    with fcol:
        status_filter = st.radio(
            "", ["Alle", "Kladde", "Planlagt", "Udgivet"],
            horizontal=True, label_visibility="collapsed",
        )
    with scol:
        st.markdown(
            '<div style="text-align:right;padding-top:8px;font-size:13px;color:#6b7280">'
            'Nyeste først ↓</div>',
            unsafe_allow_html=True,
        )

    def matches(a):
        s = art_state(a["url"])["status"]
        if status_filter == "Alle":     return True
        if status_filter == "Kladde":   return s in ("ny", "kladde")
        if status_filter == "Planlagt": return s == "planlagt"
        if status_filter == "Udgivet":  return s == "udgivet"
        return True

    filtered = [a for a in articles if matches(a)]

    if not filtered:
        st.markdown(
            '<div style="text-align:center;padding:40px;color:#9ca3af">Ingen artikler her endnu.</div>',
            unsafe_allow_html=True,
        )

    # ─── Artikel-liste ────────────────────────────────────────────────────────
    for art in filtered:
        state  = art_state(art["url"])
        url    = art["url"]
        status = state["status"]
        post   = state["post"]

        # Artikel-kort
        st.markdown(
            f'<div class="art-card">'
            f'<div class="art-title">{art["titleEn"]}</div>'
            f'<div class="art-meta">{art["date"][:10]} &nbsp;·&nbsp; {short_url(url)}</div>'
            f'{cat_badge(art["category"])} {status_badge(status)}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Knap-række
        btn_col, mark_col = st.columns([5, 2])
        with btn_col:
            btn_label = "Generer post" if not post else "Regenerer"
            do_generate = st.button(btn_label, key=f"gen_{url}", type="primary")

        with mark_col:
            if post:
                mark_options = ["Kladde", "Planlagt", "Udgivet"]
                cur_idx = {"kladde": 0, "planlagt": 1, "udgivet": 2}.get(status, 0)
                mark = st.selectbox(
                    "", mark_options, index=cur_idx,
                    key=f"mark_{url}", label_visibility="collapsed",
                )
                set_art_state(url, status=mark.lower())

        # Generering
        if do_generate:
            if not provider:
                st.session_state[f"open_manual_{url}"] = True
            else:
                with st.spinner("Genererer LinkedIn-opslag..."):
                    result, err = generate_post(art)
                if err:
                    st.error(f"Fejl: {err}")
                else:
                    set_art_state(url, status="kladde", post=result)
                    st.session_state[f"open_manual_{url}"] = False
                    st.rerun()

        # Vis genereret post
        if post:
            with st.container():
                edited = st.text_area(
                    "Redigér:", value=post, height=320, key=f"edit_{url}",
                    label_visibility="collapsed",
                )
                if edited != post:
                    set_art_state(url, post=edited)

                md_content, filename = post_to_md(art, edited)
                dl_col, _ = st.columns([2, 3])
                with dl_col:
                    st.download_button(
                        "Download .md", data=md_content.encode(),
                        file_name=filename, mime="text/markdown",
                        key=f"dl_{url}",
                    )

        # Manuel fallback (ingen nøgle)
        if st.session_state.get(f"open_manual_{url}") and not post:
            with st.container():
                st.markdown(
                    '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;'
                    'padding:12px 16px;margin:6px 0;font-size:13px;color:#92400e">'
                    'Tilføj en gratis Groq-nøgle for automatisk generering. '
                    'Indtil da: kopiér prompten nedenfor og indsæt på claude.ai.</div>',
                    unsafe_allow_html=True,
                )
                st.code(make_prompt(art), language=None)
                st.link_button("Åbn claude.ai", "https://claude.ai")
                pasted = st.text_area("Indsæt svar:", height=260, key=f"paste_{url}",
                                      placeholder="Paste teksten fra Claude her...")
                if st.button("Gem kladde", key=f"savemanual_{url}", type="primary") and pasted.strip():
                    set_art_state(url, status="kladde", post=pasted.strip())
                    st.session_state[f"open_manual_{url}"] = False
                    st.rerun()

        st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    if st.button("Hent nye artikler"):
        st.cache_data.clear()
        st.rerun()
