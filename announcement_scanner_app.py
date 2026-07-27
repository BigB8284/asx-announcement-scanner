"""
ASX ANNOUNCEMENT SCANNER — v2 (using Apify data source)
===========================================================
Run at 9:30am (half hour before open, catches overnight/early filings)
and again at 9:50am (catches anything fresh) - nothing after that is
tracked, by design, to keep this fast and simple.
 
Shows exactly ONE top long pick and ONE top short pick - not a ranked
list. For a live stream like announcements, waiting to compare against
"everything today" would defeat the whole point of speed.
 
DATA SOURCE: direct scraping of ASX's own site got blocked by their
anti-bot protection (confirmed - not something we could fix with code).
This version uses the Apify "ASX Company Announcements" actor instead,
which handles that problem properly. Costs a small amount per run
(~$0.05 per announcement pulled), covered by Apify's free $5/month
credit for normal usage levels.
 
FILTERING (v1): uses ASX's own "market sensitive" flag to cut out
routine noise. KNOWN GAP: some genuinely important announcements
(e.g. quarterly reports) aren't always flagged this way - a fix for
this is planned for a future session once we verify the exact filter
syntax needed.
 
KNOWN LIMITATION: only reads the announcement HEADLINE, not the full
PDF text. Reading full documents is a bigger v2 build.
"""
 
import streamlit as st
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
 
st.set_page_config(page_title="ASX Announcement Scanner", layout="centered")
 
APIFY_ACTOR = "nexgendata~asx-company-announcements"
SYDNEY_TZ = ZoneInfo("Australia/Sydney")
 
 
def fetch_todays_announcements():
    """Fetch today's market-sensitive ASX announcements via Apify."""
    apify_token = st.secrets.get("APIFY_API_TOKEN") if hasattr(st, "secrets") else None
    if not apify_token:
        return None, "No Apify API token found in Streamlit Secrets (add APIFY_API_TOKEN)."
 
    try:
        url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
        params = {"token": apify_token}
        payload = {"marketSensitiveOnly": True, "maxResults": 60}  # higher since this runs once/day and must catch everything - costs ~$3/run at $0.05 each
 
        response = requests.post(url, params=params, json=payload, timeout=120)
        response.raise_for_status()
        items = response.json()
 
        today_str = datetime.now(SYDNEY_TZ).strftime("%Y-%m-%d")
        announcements = []
        for item in items:
            company = item.get("company_name", "").strip()
            headline = item.get("headline", "").strip()
            time_str = item.get("announcement_time", "")
            ann_date = item.get("announcement_date", "")
            # Skip anything not from today - this actor doesn't support a
            # date filter itself, so we filter client-side after the fact
            if today_str not in str(ann_date):
                continue
            if company and headline:
                announcements.append({
                    "time": time_str,
                    "company": company,
                    "title": headline,
                })
        return announcements, None
    except requests.exceptions.RequestException as e:
        return None, f"Couldn't reach Apify: {e}"
    except Exception as e:
        return None, f"Something went wrong processing the results: {e}"
 
 
def analyze_announcements(announcement_list):
    """Send today's market-sensitive announcement headlines to Claude
    Haiku, asking for the single best long pick and single best short
    pick with a terse reason each."""
    api_key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No Anthropic API key found in Streamlit Secrets."
 
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
 
        listing = "\n".join(f"{a['company']}: {a['title']}" for a in announcement_list)
 
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=(
                "You are helping a discretionary ASX day trader who needs to act fast. "
                "You will be given a list of today's market-sensitive ASX announcement "
                "headlines (company: headline). From this list, pick exactly ONE headline "
                "that looks most likely to move its stock UP (a long idea) and exactly "
                "ONE that looks most likely to move its stock DOWN (a short idea). "
                "If nothing looks clearly bullish, say so instead of forcing a pick - same "
                "for bearish. Do NOT invent a confidence score or percentage. For each pick, "
                "give: the company name, a terse one-line reason (under 15 words), and note "
                "if the headline alone feels ambiguous or would benefit from reading the full "
                "document. Format your response as:\n\n"
                "LONG: [company] - [reason]\n"
                "SHORT: [company] - [reason]\n\n"
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
    now = datetime.now(SYDNEY_TZ)
    st.write(f"**Scanned:** {now.strftime('%d %b %Y, %I:%M %p')} AEST")
 
    with st.spinner("Fetching today's ASX announcements..."):
        announcements, fetch_error = fetch_todays_announcements()
 
    if fetch_error:
        st.error(fetch_error)
    elif not announcements:
        st.info("No market-sensitive announcements found right now.")
    else:
        st.caption(f"{len(announcements)} market-sensitive announcements found")
 
        with st.spinner("Analyzing with Claude..."):
            analysis, ai_error = analyze_announcements(announcements)
 
        if ai_error:
            st.error(ai_error)
            st.caption("Showing the raw list instead:")
            for a in announcements:
                st.caption(f"{a['time']} — **{a['company']}**: {a['title']}")
        else:
            st.divider()
            st.subheader("Today's Picks")
            st.code(analysis, language=None)
 
        with st.expander(f"See all {len(announcements)} market-sensitive announcements today"):
            for a in announcements:
                st.caption(f"{a['time']} — **{a['company']}**: {a['title']}")
else:
    st.info("Tap 'Scan Announcements' to check today's filings.")
 
