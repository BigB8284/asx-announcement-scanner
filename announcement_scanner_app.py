"""
ASX ANNOUNCEMENT SCANNER
==========================
Run at 9:30am (half hour before open, catches overnight/early filings)
and again at 9:50am (catches anything fresh) - nothing after that is
tracked, by design, to keep this fast and simple.
 
Shows exactly ONE top long pick and ONE top short pick - not a ranked
list. For a live stream like announcements, waiting to compare against
"everything today" would defeat the whole point of speed.
 
How the filtering works (two stages, to keep AI costs low and avoid
noise):
1. ASX itself flags certain announcements as "price sensitive" under
   the ASX Listing Rules - this is real, existing data, not something we
   invented. We only look at price-sensitive announcements, which
   already cuts out routine filings (director's interest notices,
   standard forms, etc.)
2. Claude Haiku reads the remaining headlines and picks the single best
   long candidate and single best short candidate, with a terse
   one-line reason - no invented confidence score, just a direct read.
 
KNOWN LIMITATION (v1): only reads the announcement HEADLINE, not the
full PDF text. Titles are often informative enough, but can occasionally
be ambiguous or too brief. Reading full documents is a bigger v2 build.
 
KNOWN RISK: this scrapes ASX's public announcements page, which could
not be tested against the live internet during development. If this
throws an error on your first run, that's the most likely place
something needs adjusting - screenshot it and we'll fix it together.
"""
 
import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
 
st.set_page_config(page_title="ASX Announcement Scanner", layout="centered")
 
ASX_ANNOUNCEMENTS_URL = "https://www.asx.com.au/asx/v2/statistics/todayAnns.do"
 
 
def fetch_todays_announcements():
    """Fetch and parse today's ASX announcements list. Returns a list of
    dicts: {time, code, title, price_sensitive}."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(ASX_ANNOUNCEMENTS_URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
 
        announcements = []
        table = soup.find("table")
        if table is None:
            return None, "Couldn't find the announcements table on the page - ASX may have changed their page layout."
 
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            time_str = cells[0].get_text(strip=True)
            code = cells[1].get_text(strip=True)
            title_cell = cells[2]
            title = title_cell.get_text(strip=True)
            # ASX marks price-sensitive announcements with a "*" or similar
            # marker next to the title - check for common indicators
            price_sensitive = "*" in title or "price sensitive" in title.lower() or bool(title_cell.find("b"))
            title_clean = title.replace("*", "").strip()
 
            if code and title_clean:
                announcements.append({
                    "time": time_str,
                    "code": code,
                    "title": title_clean,
                    "price_sensitive": price_sensitive,
                })
 
        return announcements, None
    except requests.exceptions.RequestException as e:
        return None, f"Couldn't reach ASX's announcements page: {e}"
    except Exception as e:
        return None, f"Something went wrong parsing the page: {e}"
 
 
def analyze_announcements(price_sensitive_list):
    """Send the day's price-sensitive announcement headlines to Claude
    Haiku, asking for the single best long pick and single best short
    pick with a terse reason each."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No Anthropic API key found in Streamlit Secrets."
 
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
 
        listing = "\n".join(f"{a['code']}: {a['title']}" for a in price_sensitive_list)
 
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=(
                "You are helping a discretionary ASX day trader who needs to act fast. "
                "You will be given a list of today's price-sensitive ASX announcement "
                "headlines (ticker: headline). From this list, pick exactly ONE headline "
                "that looks most likely to move its stock UP (a long idea) and exactly "
                "ONE that looks most likely to move its stock DOWN (a short idea). "
                "If nothing looks clearly bullish, say so instead of forcing a pick - same "
                "for bearish. Do NOT invent a confidence score or percentage. For each pick, "
                "give: the ticker, a terse one-line reason (under 15 words), and note if the "
                "headline alone feels ambiguous or would benefit from reading the full "
                "document. Format your response as:\n\n"
                "LONG: [ticker] - [reason]\n"
                "SHORT: [ticker] - [reason]\n\n"
                "If no clear long or short candidate exists, write 'LONG: None found' or "
                "'SHORT: None found' instead."
            ),
            messages=[{"role": "user", "content": listing}],
        )
        return response.content[0].text, None
    except Exception as e:
        return None, f"AI analysis failed: {e}"
       
 
st.title("ASX Announcement Scanner")
st.caption("Run at 9:30am and again at 9:50am. Shows one top long pick and one top short pick.")
 
if st.button("Scan Announcements", type="primary", use_container_width=True):
    now = datetime.now()
    st.write(f"**Scanned:** {now.strftime('%d %b %Y, %I:%M %p')}")
 
    with st.spinner("Fetching today's ASX announcements..."):
        announcements, fetch_error = fetch_todays_announcements()
 
    if fetch_error:
        st.error(fetch_error)
        st.caption("This is the riskiest part of this tool technically - screenshot this error and we'll fix it together.")
    elif not announcements:
        st.warning("No announcements found - could be before market data is available yet, or a parsing issue.")
    else:
        price_sensitive = [a for a in announcements if a["price_sensitive"]]
 
        st.caption(f"{len(announcements)} total announcements today, {len(price_sensitive)} flagged price-sensitive")
 
        if not price_sensitive:
            st.info("No price-sensitive announcements yet today.")
        else:
            with st.spinner("Analyzing with Claude..."):
                analysis, ai_error = analyze_announcements(price_sensitive)
 
            if ai_error:
                st.error(ai_error)
                st.caption("Showing the raw price-sensitive list instead:")
                for a in price_sensitive:
                    st.caption(f"{a['time']} — **{a['code']}**: {a['title']}")
            else:
                st.divider()
                st.subheader("Today's Picks")
                st.code(analysis, language=None)
 
            with st.expander(f"See all {len(price_sensitive)} price-sensitive announcements today"):
                for a in price_sensitive:
                    st.caption(f"{a['time']} — **{a['code']}**: {a['title']}")
else:
    st.info("Tap 'Scan Announcements' to check today's filings.")
 
