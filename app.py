import streamlit as st
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
def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

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
                save_dossier(new_acc_id, seeded, "", "", "")
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
    account = get_account(acc_id)
    dossier_row = get_dossier(acc_id)
    notes = get_notes(acc_id)
    linked_cases = get_linked_cases(acc_id)
    st.divider()
    st.subheader("Dossier")

    dossier_text = st.text_area(
        "Dossier",
        value=dossier_row.get("dossier") or "",
        height=420,
        key="dossier_left"
)


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
    "Stakeholders"
])

    dossier_text = dossier_row.get("dossier") or ""
    stakeholders_text = dossier_row.get("stakeholders") or ""
    messages_text = dossier_row.get("messages") or ""
    scan_text = dossier_row.get("business_scan") or ""

    with tabs[0]:
       pass

    with tabs[1]:
        st.info("Progress is tracked via notes.")

    with tabs[2]:
        messages_text = st.text_area("Messages", value=messages_text, height=260)

    with tabs[3]:
        st.write(f"Industry: {account.get('industry','')}")
        st.write(f"Segment: {account.get('segment','')}")
        st.write(f"Status: {account.get('status','')}")
        scan_text = st.text_area("Business scan", value=scan_text, height=240)

    with tabs[4]:
        case_search = st.text_input("Search cases")
        all_cases = get_cases(case_search)
        linked_ids = {c["id"] for c in linked_cases}
    
    with tabs[5]:
        st.subheader("Notes")

    # Add note (boven)
    top_l, top_r = st.columns([1, 1])

    with top_l:
        note_date = st.date_input("Note date", value=date.today(), key="notes_tab_date")
        note_type = st.selectbox(
            "Type",
            ["LinkedIn", "Email", "Call", "Meeting", "Internal", "Note"],
            key="notes_tab_type"
        )

    with top_r:
        stage = st.selectbox(
            "Stage",
            ["New", "Outreach", "Engaged", "Meeting", "Proposal", "Won", "Lost"],
            key="notes_tab_stage"
        )

    note_text = st.text_area("Add note", height=140, key="notes_tab_text")

    if st.button("Add note", key="notes_tab_add"):
        if note_text.strip():
            add_note(acc_id, note_date, note_type, stage, note_text.strip())
            st.success("Note added.")
            st.rerun()
        else:
            st.warning("Note is empty.")

    st.divider()

    # Notes overview (grote read-only viewer)
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

    st.text_area(
        "Notes overview (newest first)",
        value=notes_overview,
        height=520,
        disabled=True,
        key="notes_overview_big"
    )

    st.markdown(
        f"➡️ **Open full-page Notes:** "
        f"[Open Notes focus](?focus=notes&acc_id={acc_id}) "
        f"(Ctrl/⌘-click for new tab)"
    )


with tabs[6]:
    st.subheader("Stakeholders")

    stakeholders_text = st.text_area(
        "Stakeholders",
        value=stakeholders_text,
        height=520,
        key="stakeholders_text_area"
    )
  with tabs[7]:
    st.subheader("Sales Copilot")

    copilot_text = dossier_row.get("copilot_snapshot") or ""
    copilot_text = st.text_area(
        "Copilot Snapshot (AI-ready, paste output here)",
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

mode = st.selectbox("Generate prompt for", ["Update dossier", "Stakeholders", "Message pack", "Business scan"])
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

st.text_area("Prompt", value=prompt, height=220)
ai_out = st.text_area("AI output", height=220)

if st.button("Apply AI output"):
    if ai_out.strip():
        if mode == "Update dossier":
            dossier_text = ai_out.strip()
        elif mode == "Stakeholders":
            stakeholders_text = ai_out.strip()
        elif mode == "Message pack":
            messages_text = ai_out.strip()
        else:
            scan_text = ai_out.strip()

        save_dossier(acc_id, dossier_text, stakeholders_text, messages_text, scan_text)
        st.success("Applied.")
        st.rerun()

