import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client
from datetime import date, datetime, timezone

st.set_page_config(page_title="Sales Dossier Tool", layout="wide")

# --------- Supabase ----------
@st.cache_resource
def sb():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

db = sb()

# --------- Helpers ----------
def copy_button(text: str, label: str = "Copy"):
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    html = f"""
    <div style="display:flex; justify-content:flex-end; margin-top:4px; margin-bottom:4px;">
      <button id="copybtn" style="
        padding:6px 10px; border:1px solid #ccc; border-radius:6px;
        background:#f7f7f7; cursor:pointer;">
        {label}
      </button>
    </div>
    <script>
      const btn = document.getElementById('copybtn');
      btn.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(`{safe}`);
          btn.innerText = 'Copied ✅';
          setTimeout(() => btn.innerText = '{label}', 1200);
        }} catch (e) {{
          btn.innerText = 'Copy failed';
          setTimeout(() => btn.innerText = '{label}', 1200);
        }}
      }});
    </script>
    """
    components.html(html, height=45)

def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
import re

ACTION_CUES = [
    "follow up", "follow-up", "opvolg", "stuur", "send", "mail", "email", "deel",
    "plan", "afspraak", "meeting", "call", "demo", "proposal", "offerte",
    "security", "legal", "procurement", "inkoop", "budget", "pricing", "prijs",
    "stakeholder", "beslisser", "decision", "timeline", "deadline", "next step",
    "volgende stap", "actie", "to do", "todo"
]

ROLE_KEYWORDS = {
    "economic_buyer": ["ceo", "cfo", "directeur", "vp", "md", "gm", "budget owner", "eigenaar"],
    "champion": ["champion", "sponsor", "voorvechter", "ambassadeur"],
    "technical_buyer": ["it", "cto", "architect", "security", "ciso", "infra", "integratie"],
    "user_lead": ["operations", "manager", "teamlead", "hoofd", "super user", "key user", "operatie"],
    "procurement": ["procurement", "inkoop", "purchasing", "vendor", "contract"],
    "legal": ["legal", "juridisch", "privacy", "dpa", "msa", "contract"],
}

DEFAULT_ROLES_CHECKLIST = [
    ("Economic Buyer", "economic_buyer"),
    ("Champion / Sponsor", "champion"),
    ("Technical Buyer (IT/Security)", "technical_buyer"),
    ("User Lead (Operations)", "user_lead"),
    ("Procurement / Inkoop", "procurement"),
    ("Legal / Privacy", "legal"),
]

STAGE_EXIT_CRITERIA = {
    "New": [
        "ICP fit helder (wie/waarom nu?)",
        "Eerste outreach + reactie of signaal van interesse",
    ],
    "Outreach": [
        "Eerste gesprek gepland of warm intro gevraagd",
        "Probleem/pijn hypothese gedeeld + bevestigd/ontkracht",
    ],
    "Engaged": [
        "Discovery gedaan: pijn + impact + stakeholders",
        "Volgende stap afgesproken met datum",
    ],
    "Meeting": [
        "Buying process duidelijk (stappen + timing)",
        "Decision criteria + success metrics helder",
        "Champion geïdentificeerd (of plan om te vinden)",
    ],
    "Proposal": [
        "Scope + prijs + ROI/impact afgestemd",
        "Procurement/legal/security pad bekend",
        "Mutual Action Plan met deadlines",
    ],
}

def _norm(s: str) -> str:
    return (s or "").lower().strip()

def extract_candidate_actions(notes, max_items=8):
    """
    Heuristiek: pak zinnen/bullets uit recente notes met action cues.
    Output: list[str]
    """
    items = []
    for n in notes[:25]:
        txt = (n.get("content") or "").strip()
        if not txt:
            continue

        lines = [l.strip(" -•\t") for l in re.split(r"[\n\r]+", txt) if l.strip()]
        for line in lines:
            ln = _norm(line)
            if any(cue in ln for cue in ACTION_CUES):
                d = n.get("note_date") or ""
                items.append(f"[{d}] {line}")
                if len(items) >= max_items:
                    return items
    return items

def stakeholder_coverage(stakeholders_text: str):
    stxt = _norm(stakeholders_text)
    cov = {}
    for role_key, kws in ROLE_KEYWORDS.items():
        cov[role_key] = any(kw in stxt for kw in kws)
    return cov

def detect_stakeholder_gaps(stakeholders_text: str):
    cov = stakeholder_coverage(stakeholders_text)
    gaps = []
    for label, key in DEFAULT_ROLES_CHECKLIST:
        if not cov.get(key, False):
            gaps.append(label)
    return gaps

def infer_stage_from_data(account_status: str, notes):
    status = (account_status or "").strip() or "New"
    recent = _norm(" ".join([
        (n.get("note_type") or "") + " " + (n.get("stage") or "") + " " + (n.get("content") or "")
        for n in notes[:10]
    ]))

    if "proposal" in recent or "offerte" in recent:
        return "Proposal"
    if "meeting" in recent or "demo" in recent or "call" in recent:
        return "Meeting"
    return status

def stage_signals(notes, stakeholders_text, linked_cases):
    blob = _norm(
        " ".join([(n.get("content") or "") for n in notes[:25]]) + " " +
        (stakeholders_text or "") + " " +
        " ".join([(c.get("content") or "") for c in linked_cases])
    )
    return {
        "impact": any(k in blob for k in ["impact", "€", "eur", "kpi", "besparing", "efficiency", "risico", "risk"]),
        "buying_process": any(k in blob for k in ["procurement", "inkoop", "legal", "security", "dpa", "msa", "proces", "tender"]),
        "decision_criteria": any(k in blob for k in ["criteria", "succes", "success", "must have", "requirements", "eisen"]),
        "next_step_date": any(k in blob for k in ["volgende week", "next week", "afspraak", "gepland", "calendar", "uitnodiging", "datum"]),
        "champion": any(k in _norm(stakeholders_text) for k in ROLE_KEYWORDS["champion"]),
    }

DEFAULT_DOSSIER_TEMPLATE = """# Account Dossier — {account_name}

## Account Snapshot
- Company:
- Industry:
- Segment:
- Geography:
- Status:
- Priority:
- Deal size:
- Next action:

## Stakeholders (summary)
- 

## Observations (signals)
- 

## Hypotheses (pains / triggers)
- 
- 
- 

## Open Questions (to validate)
- 
- 
- 

## Next Best Actions (max 5)
- 
"""

def get_accounts(search=""):
    q = db.table("accounts").select("*").order("updated_at", desc=True)
    if search.strip():
        q = q.ilike("name", f"%{search.strip()}%")
    res = q.execute()
    return res.data or []

def upsert_account(payload):
    # Supabase upsert needs conflict target; we do: try insert, if fails update by name
    name = payload["name"].strip()
    existing = db.table("accounts").select("id").eq("name", name).execute().data
    if existing:
        acc_id = existing[0]["id"]
        payload["updated_at"] = now_iso()
        db.table("accounts").update(payload).eq("id", acc_id).execute()
        return acc_id
    payload["updated_at"] = now_iso()
    res = db.table("accounts").insert(payload).execute()
    return res.data[0]["id"]

def get_account(acc_id):
    res = db.table("accounts").select("*").eq("id", acc_id).single().execute()
    return res.data

def get_dossier(acc_id):
    res = db.table("dossiers").select("*").eq("account_id", acc_id).execute().data
    if res:
        return res[0]
    # create empty row
    db.table("dossiers").insert({"account_id": acc_id, "updated_at": now_iso()}).execute()
    return db.table("dossiers").select("*").eq("account_id", acc_id).single().execute().data

def save_dossier(acc_id, dossier, stakeholders, messages, business_scan, copilot_snapshot):
    db.table("dossiers").update({
        "dossier": dossier,
        "stakeholders": stakeholders,
        "messages": messages,
        "business_scan": business_scan,
        "copilot_snapshot": copilot_snapshot,
        "updated_at": now_iso()
    }).eq("account_id", acc_id).execute()
    db.table("accounts").update({"updated_at": now_iso()}).eq("id", acc_id).execute()

def add_note(acc_id, note_date, note_type, stage, content):
    db.table("notes").insert({
        "account_id": acc_id,
        "note_date": str(note_date),
        "note_type": note_type,
        "stage": stage,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()
    db.table("accounts").update({"updated_at": now_iso()}).eq("id", acc_id).execute()


def update_note(note_id, new_content, new_note_date=None):
    payload = {"content": new_content}
    if new_note_date is not None:
        payload["note_date"] = str(new_note_date)
    db.table("notes").update(payload).eq("id", note_id).execute()


def delete_note(note_id):
    db.table("notes").delete().eq("id", note_id).execute()



    db.table("notes").insert({
        "account_id": acc_id,
        "note_date": str(note_date),
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()
    db.table("accounts").update({"updated_at": now_iso()}).eq("id", acc_id).execute()

def get_notes(acc_id, limit=50):
    res = (db.table("notes")
           .select("*")
           .eq("account_id", acc_id)
           .order("created_at", desc=True)
           .limit(limit)
           .execute())
    return res.data or []

def add_case(title, industry, tags, content):
    db.table("cases").insert({
        "title": title,
        "industry": industry,
        "tags": tags,
        "content": content
    }).execute()

def get_cases(search=""):
    q = db.table("cases").select("*").order("created_at", desc=True)
    if search.strip():
        q = q.or_(f"title.ilike.%{search}%,tags.ilike.%{search}%")
    return q.execute().data or []

def link_case(acc_id, case_id, linked: bool):
    if linked:
        db.table("account_cases").upsert({"account_id": acc_id, "case_id": case_id}).execute()
    else:
        db.table("account_cases").delete().eq("account_id", acc_id).eq("case_id", case_id).execute()

def get_linked_cases(acc_id):
    links = db.table("account_cases").select("case_id").eq("account_id", acc_id).execute().data or []
    if not links:
        return []
    ids = [l["case_id"] for l in links]
    return db.table("cases").select("*").in_("id", ids).execute().data or []

def build_prompt(mode, account, dossier_row, notes, linked_cases):
    dossier_text = dossier_row.get("dossier") or ""
    stakeholders_text = dossier_row.get("stakeholders") or ""
    messages_text = dossier_row.get("messages") or ""
    scan_text = dossier_row.get("business_scan") or ""

    notes_block = "\n\n".join([f"[{n['note_date']}] {n['content']}" for n in notes[:10]]) or "(none)"
    cases_block = "\n\n".join([f"CASE: {c['title']}\nIndustry: {c.get('industry','')}\nTags: {c.get('tags','')}\n{c['content']}" for c in linked_cases]) or "(none)"

    today = date.today().isoformat()
    if mode == "Smart Suggestions":
        candidates = extract_candidate_actions(notes, max_items=8)
        gaps = detect_stakeholder_gaps(stakeholders_text)
        inferred_stage = infer_stage_from_data(account.get("status",""), notes)
        sig = stage_signals(notes, stakeholders_text, linked_cases)

        candidates_block = "\n".join([f"- {c}" for c in candidates]) or "- (none found)"
        gaps_block = "\n".join([f"- {g}" for g in gaps]) or "- (no obvious gaps)"

        criteria = STAGE_EXIT_CRITERIA.get(inferred_stage, [])
        criteria_lines = []
        for c in criteria:
            lc = c.lower()
            mark = "❓"
            if "impact" in lc and sig["impact"]:
                mark = "✅"
            if ("buying process" in lc or "procurement" in lc) and sig["buying_process"]:
                mark = "✅"
            if ("decision criteria" in lc or "success" in lc or "metrics" in lc) and sig["decision_criteria"]:
                mark = "✅"
            if ("volgende stap" in lc or "datum" in lc) and sig["next_step_date"]:
                mark = "✅"
            if ("champion" in lc) and sig["champion"]:
                mark = "✅"
            criteria_lines.append(f"- {mark} {c}")
        criteria_block = "\n".join(criteria_lines) or "- (no criteria for this stage)"

        return f"""ROLE
You are my B2B sales copilot. Be concrete and specific. No generic advice.

ACCOUNT
- Name: {account.get('name','')}
- Industry: {account.get('industry','')}
- Segment: {account.get('segment','')}
- Geography: {account.get('geography','')}
- Current Status: {account.get('status','')}
- Inferred Stage: {inferred_stage}

DOSSIER (context)
<<<
{dossier_text}
>>>

STAKEHOLDERS (raw)
<<<
{stakeholders_text}
>>>

NOTES (newest first)
<<<
{notes_block}
>>>

LINKED CASES (optional)
<<<
{cases_block}
>>>

LOCAL SIGNALS (from heuristics)
Candidate actions found:
{candidates_block}

Stakeholder gaps (roles not clearly covered):
{gaps_block}

Stage exit criteria check ({inferred_stage}):
{criteria_block}

GOAL
Generate Smart Suggestions to progress the account.

OUTPUT FORMAT (4 sections)
1) NEXT BEST ACTIONS (max 5)
- Title (imperative)
- Why now (1 line)
- Evidence (quote or reference from notes/signals)
- Priority (H/M/L)
- Owner (Me/Customer)
- Suggested due date

2) QUESTIONS FOR NEXT MEETING (max 10)
Group by: Pain/Impact, Process, People, Timing/Risk.
For each question: Intent (what it validates)

3) STAKEHOLDER GAPS
- Missing roles + risk if missing
- How to ask for introduction (1–2 suggested lines)

4) ACCOUNT PROGRESSION
- Current stage confidence (0–100%)
- What is missing to move 1 stage forward (top 3)
- Suggested next milestone + mutual action plan bullets

RULES
- Base everything on the inputs. If something is missing, label it as ASSUMPTION + add a validation question.
- Keep it crisp, scannable bullets.
"""
    if mode == "Update dossier":
        return f"""ROLE
You are my sales assistant. Think proactively and stay structured.

INPUT
DOSSIER (current)
<<<
{dossier_text}
>>>

STAKEHOLDERS (current)
<<<
{stakeholders_text}
>>>

NOTES (new input, newest first)
<<<
{notes_block}
>>>

LINKED CASES (optional)
<<<
{cases_block}
>>>

GOAL
Update the dossier so I can progress this account.

INSTRUCTIONS
1) Keep structure; do not delete existing content.
2) Improve clarity + add missing info where helpful.
3) Mark all new additions with: [New - {today}]
4) Add/refresh: Hypotheses, Open Questions, Next Best Actions (max 5).
5) Keep it scannable (bullets, short lines).

OUTPUT
Return TWO blocks:
A) CHANGELOG (max 8 bullets)
B) UPDATED DOSSIER (full text)
"""
    if mode == "Message pack":
        return f"""Use the information below to produce a role-aware message pack.

DOSSIER
<<<
{dossier_text}
>>>

NOTES
<<<
{notes_block}
>>>

LINKED CASES (optional)
<<<
{cases_block}
>>>

OUTPUT (same tone of voice, professional, human):
1) LinkedIn connect message (<=300 characters)
2) Follow-up #1 (short)
3) Follow-up #2 (short, value/insight)
4) Procurement angle (cost/risk/contract)
5) C-level angle (impact, risk, value)
6) 3 optional email subject lines

RULES:
- Personalize to role/industry.
- No buzzwords, no marketing fluff.
- End with a simple CTA (15 min / quick chat).
"""
    if mode == "Business scan":
        return f"""Create or update a 1-page Business Scan using the info below.

DOSSIER
<<<
{dossier_text}
>>>

NOTES
<<<
{notes_block}
>>>

LINKED CASES (optional)
<<<
{cases_block}
>>>

STRUCTURE:
1) Situation (3 bullets)
2) Pains (validated vs assumptions)
3) Impact (ops/financial/risk)
4) Hypotheses + how to validate
5) Scope options:
   - Light (2–4 weeks)
   - Medium (6–10 weeks)
6) Needed stakeholders
7) Next steps (concrete)

RULES:
- Crisp, practical, sales-usable.
- Avoid jargon.
"""
    if mode == "Stakeholders":
        return f"""Build/update a stakeholder map.

DOSSIER
<<<
{dossier_text}
>>>

NOTES
<<<
{notes_block}
>>>

OUTPUT:
- Stakeholder list (name/role if known, otherwise role)
- Influence level (High/Med/Low)
- Likely KPIs / priorities
- Objections / risks
- Best entry approach + messaging angle per stakeholder
- Who to approach first and why (top 3)
"""
    return ""
# --------- UI ----------
st.title("Sales Dossier Tool (Copy/Paste AI Flow)")

# --- Sidebar: Create / Edit Account ---
with st.sidebar:
    st.header("Create / Edit Account")
    name = st.text_input("Account name")
    industry = st.text_input("Industry")
    segment = st.selectbox("Segment", ["", "SMB", "Mid-market", "Enterprise"], index=0)
    geography = st.text_input("Geography")
    status = st.selectbox("Status", ["New", "Outreach", "Engaged", "Meeting", "Proposal", "Won", "Lost"])
    priority = st.selectbox("Priority", ["A", "B", "C"], index=1)
    deal_size = st.text_input("Deal size (optional)")
    next_action = st.text_input("Next action (short)")

    if st.button("Save account"):
        if not name.strip():
            st.warning("Account name is required.")
        else:
            new_acc_id = upsert_account({
                "name": name.strip(),
                "industry": industry.strip(),
                "segment": segment,
                "geography": geography.strip(),
                "status": status,
                "priority": priority,
                "deal_size": deal_size.strip(),
                "next_action": next_action.strip()
            })
            d = get_dossier(new_acc_id)
            if not d.get("dossier"):
                seeded = DEFAULT_DOSSIER_TEMPLATE.format(account_name=name.strip())
                save_dossier(new_acc_id, seeded, "", "", "", "")
            st.success("Saved.")
            st.rerun()

# --- Main Layout ---
left, middle, right = st.columns([1, 2, 1])

# --- LEFT: Account selector ---
with left:
    st.subheader("Accounts")
    search = st.text_input("Search accounts")
    accounts = get_accounts(search)

    if not accounts:
        st.info("No accounts yet. Create one in the sidebar.")
        st.stop()

    label_to_id = {
        f"{a['name']} · {a.get('status','')} · P{a.get('priority','B')}": a["id"]
        for a in accounts
    }
    pick = st.selectbox("Select account", list(label_to_id.keys()))
    acc_id = label_to_id[pick]

# --- Load account data (OUTSIDE left) ---
account = get_account(acc_id)
dossier_row = get_dossier(acc_id)
notes = get_notes(acc_id)
linked_cases = get_linked_cases(acc_id)

# --- Initialize editable fields once ---
dossier_text = dossier_row.get("dossier") or ""
stakeholders_text = dossier_row.get("stakeholders") or ""
messages_text = dossier_row.get("messages") or ""
scan_text = dossier_row.get("business_scan") or ""
copilot_text = dossier_row.get("copilot_snapshot") or ""



# --- Shared data (SAFE: acc_id is guaranteed here) ---

# --- Focus view handler (opens with ?focus=notes&acc_id=...) ---
qp = st.query_params
if qp.get("focus") == "notes" and qp.get("acc_id") == str(acc_id):
    st.title(f"Notes Focus — {account.get('name','')}")
    st.caption("Tip: close this tab to return to the main workspace.")

    def _local_ts(iso_str: str) -> str:
        if not iso_str:
            return ""
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%d-%m-%Y %H:%M")

    notes_overview = "\n\n".join([
        f"{n.get('note_date','')} | {_local_ts(n.get('created_at',''))} | {n.get('note_type','')} | {n.get('stage','')}\n"
        f"{n.get('content','')}"
        for n in notes[:200]
    ]) or "(no notes yet)"

    st.text_area("Notes (focus)", value=notes_overview, height=750, disabled=True)
    st.stop()

# --- RIGHT: General / Notes ---
with right:
    st.subheader("Copilot Snapshot")

    # Compacte account snapshot (read-only)
    st.caption(f"{account.get('industry','')} · {account.get('segment','')} · {account.get('geography','')}")
    st.write(f"**Status:** {account.get('status','')}  |  **Priority:** {account.get('priority','')}")
    if account.get("next_action"):
        st.write(f"**Next action:** {account.get('next_action')}")

    st.divider()

    # Read-only preview uit dezelfde tekst als in Sales Copilot tab
    copilot_preview = (dossier_row.get("copilot_snapshot") or "").strip()
    if not copilot_preview:
        st.info("No Copilot Snapshot yet. Use the Sales Copilot tab to paste AI output.")
    else:
        st.text_area("Preview", value=copilot_preview, height=420, disabled=True, key="copilot_preview_right")

   

# --- MIDDLE: Workspace ---
with middle:
    st.subheader("Workspace")
    tabs = st.tabs([
    "General",
    "Attachments / progress",
    "E-mail",
    "Characteristics",
    "Cases",
    "Notes",
    "Stakeholders",
    "Sales Copilot"
])

# ---- TAB 0: General ----
with tabs[0]:
    st.write(" ")

# ---- TAB 1: Attachments / progress ----
with tabs[1]:
    st.info("Progress is tracked via Notes.")

# ---- TAB 2: E-mail ----
with tabs[2]:
    messages_text = st.text_area("Messages", value=messages_text, height=260)

# ---- TAB 3: Characteristics ----
with tabs[3]:
    st.write(f"Industry: {account.get('industry','')}")
    st.write(f"Segment: {account.get('segment','')}")
    st.write(f"Geography: {account.get('geography','')}")
    st.write(f"Priority: {account.get('priority','')}")
    st.write(f"Status: {account.get('status','')}")
    scan_text = st.text_area("Business scan", value=scan_text, height=240)

# ---- TAB 4: Cases ----
with tabs[4]:
    case_search = st.text_input("Search cases", key="case_search")
    all_cases = get_cases(case_search)
    linked_ids = {c["id"] for c in linked_cases}

    for c in all_cases[:30]:
        checked = c["id"] in linked_ids
        new_checked = st.checkbox(
            f"{c['title']}  ·  {c.get('industry','')}",
            value=checked,
            key=f"case_{c['id']}"
        )
        if new_checked != checked:
            link_case(acc_id, c["id"], new_checked)
            st.rerun()

# ---- TAB 5: Notes ----
with tabs[5]:
    st.subheader("Notes")

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        note_date = st.date_input("Date", value=date.today(), key="notes_date")
    with c2:
        note_type = st.selectbox(
    "Type",
    ["LinkedIn","Email","Call","Meeting","Internal","Note"],
    index=5,  # default = Note
    key="notes_type"
)
    with c3:
        stage = st.selectbox("Stage", ["New","Outreach","Engaged","Meeting","Proposal","Won","Lost"], key="notes_stage")

    note_text = st.text_area("Add note", height=140, key="notes_text")

if st.button("Add note", key="add_note_btn"):
    if note_text.strip():
        add_note(acc_id, note_date, note_type, stage, note_text.strip())

        # maak inputveld leeg na opslaan
        st.session_state["notes_text"] = ""

        st.success("Note added.")
        st.rerun()


    st.divider()

    def _local_ts(ts):
        if not ts:
            return ""
        return datetime.fromisoformat(ts.replace("Z","+00:00")).astimezone().strftime("%d-%m-%Y %H:%M")

    notes_overview = "\n\n".join([
        f"{n.get('note_date')} | {_local_ts(n.get('created_at'))} | {n.get('note_type')} | {n.get('stage')}\n{n.get('content')}"
        for n in notes[:200]
    ]) or "(no notes yet)"

    st.text_area("Notes overview", value=notes_overview, height=520)

    st.markdown(
        f"[Open Notes full page](?focus=notes&acc_id={acc_id})  (Ctrl/⌘-click)"
    )

# ---- TAB 6: Stakeholders ----
with tabs[6]:
    st.subheader("Stakeholders")
    stakeholders_text = st.text_area(
        "Stakeholders",
        value=stakeholders_text,
        height=520,
        key="stakeholders_tab"
    )

# ---- TAB 7: Sales Copilot ----
with tabs[7]:
    st.subheader("Sales Copilot")
        # --- Smart Suggestions (local, no AI) ---
    st.markdown("### Smart Suggestions (local)")

    inferred_stage = infer_stage_from_data(account.get("status",""), notes)
    candidates = extract_candidate_actions(notes, max_items=8)
    gaps = detect_stakeholder_gaps(stakeholders_text)
    sig = stage_signals(notes, stakeholders_text, linked_cases)

    st.write("**Next best actions (candidates from Notes):**")
    if candidates:
        for c in candidates:
            st.write(f"- {c}")
    else:
        st.info("Nog geen duidelijke actie-signalen in Notes. Voeg in je meeting notes expliciet 'Actions:' of 'Next steps:' toe.")

    st.write("**Stakeholder gaps (rollen nog niet duidelijk afgedekt):**")
    if gaps:
        for g in gaps:
            st.write(f"- {g}")
    else:
        st.success("Geen evidente stakeholder gaps gedetecteerd (op basis van keywords).")

    st.write(f"**Stage (inferred): {inferred_stage}**")
    criteria = STAGE_EXIT_CRITERIA.get(inferred_stage, [])
    if criteria:
        for c in criteria:
            # simpele checkmarks o.b.v. signals
            lc = c.lower()
            mark = "❓"
            if "impact" in lc and sig["impact"]:
                mark = "✅"
            if ("buying process" in lc or "procurement" in lc) and sig["buying_process"]:
                mark = "✅"
            if ("decision criteria" in lc or "success" in lc or "metrics" in lc) and sig["decision_criteria"]:
                mark = "✅"
            if ("volgende stap" in lc or "datum" in lc) and sig["next_step_date"]:
                mark = "✅"
            if ("champion" in lc) and sig["champion"]:
                mark = "✅"
            st.write(f"- {mark} {c}")

    with st.expander("Generate Smart Suggestions prompt (copy/paste to AI)", expanded=False):
        smart_prompt = build_prompt(
            "Smart Suggestions",
            account,
            {
                "dossier": dossier_text,
                "stakeholders": stakeholders_text,
                "messages": messages_text,
                "business_scan": scan_text,
            },
            notes,
            linked_cases,
        )

        c1, c2 = st.columns([6, 1])
        with c1:
            st.text_area("Smart Suggestions Prompt", value=smart_prompt, height=260, key="smart_prompt_box")
        with c2:
            copy_button(smart_prompt, label="Copy")

    copilot_text = dossier_row.get("copilot_snapshot") or ""
    copilot_text = st.text_area(
        "Copilot Snapshot (paste AI output here)",
        value=copilot_text,
        height=520,
        key="copilot_snapshot_tab"
    )

    if st.button("Save workspace"):
        save_dossier(
            acc_id,
            dossier_text,
            stakeholders_text,
            messages_text,
            scan_text,
            copilot_text if "copilot_text" in locals() else (dossier_row.get("copilot_snapshot") or "")
    )
    st.success("Saved.")

# --- AI Copy / Paste ---
st.divider()
st.subheader("AI Copy / Paste")

mode = st.selectbox(
    "Generate prompt for",
    ["Smart Suggestions", "Update dossier", "Stakeholders", "Message pack", "Business scan"]
)
prompt = build_prompt(
    mode,
    account,
    {
        "dossier": dossier_text,
        "stakeholders": stakeholders_text,
        "messages": messages_text,
        "business_scan": scan_text,
    },
    notes,
    linked_cases,
)

c_prompt, c_btn = st.columns([6, 1])
with c_prompt:
    st.text_area("Prompt", value=prompt, height=220)
with c_btn:
    copy_button(prompt, label="Copy prompt")

ai_out = st.text_area("AI output", height=220)
if st.button("Apply AI output"):
    if ai_out.strip():
        if mode == "Update dossier":
            dossier_text = ai_out.strip()
        elif mode == "Stakeholders":
            stakeholders_text = ai_out.strip()
        elif mode == "Message pack":
            messages_text = ai_out.strip()
        elif mode == "Business scan":
            scan_text = ai_out.strip()
        elif mode == "Smart Suggestions":
            # Zet AI output direct in Copilot Snapshot
            copilot_text = ai_out.strip()
        else:
            scan_text = ai_out.strip()

        save_dossier(
            acc_id,
            dossier_text,
            stakeholders_text,
            messages_text,
            scan_text,
            copilot_text
        )
        st.success("Applied.")
        st.rerun()


