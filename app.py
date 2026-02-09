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

def save_dossier(acc_id, dossier, stakeholders, messages, business_scan):
    db.table("dossiers").update({
        "dossier": dossier,
        "stakeholders": stakeholders,
        "messages": messages,
        "business_scan": business_scan,
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
            acc_id = upsert_account({
                "name": name.strip(),
                "industry": industry.strip(),
                "segment": segment,
                "geography": geography.strip(),
                "status": status,
                "priority": priority,
                "deal_size": deal_size.strip(),
                "next_action": next_action.strip()
            })
            # init dossier if empty
            d = get_dossier(acc_id)
            if not d.get("dossier"):
                seeded = DEFAULT_DOSSIER_TEMPLATE.format(account_name=name.strip()).replace("- Industry:", f"- Industry: {industry.strip()}")
                save_dossier(acc_id, seeded, "", "", "")
            st.success("Saved.")
            st.rerun()

st.subheader("Accounts")
search = st.text_input("Search accounts")
accounts = get_accounts(search)

if not accounts:
    st.info("No accounts yet. Create one in the sidebar.")
    st.stop()

label_to_id = {f"{a['name']}  ·  {a.get('status','')}  ·  P{a.get('priority','B')}": a["id"] for a in accounts}
pick = st.selectbox("Select account", list(label_to_id.keys()))
acc_id = label_to_id[pick]

account = get_account(acc_id)
dossier_row = get_dossier(acc_id)
notes = get_notes(acc_id)
linked_cases = get_linked_cases(acc_id)

c1, c2 = st.columns([1, 1])

with c1:
    st.markdown("### Notes")
    note_date = st.date_input("Note date", value=date.today())
    note_type = st.selectbox("Type", ["LinkedIn", "Email", "Call", "Meeting", "Internal", "Note"])
    stage = st.selectbox("Stage", ["New", "Outreach", "Engaged", "Meeting", "Proposal", "Won", "Lost"])
    note_text = st.text_area("Paste LinkedIn snippets / meeting notes here", height=180)

    if st.button("Add note"):
        if note_text.strip():
            add_note(acc_id, note_date, note_type, stage, note_text.strip())
            st.success("Note added.")
            st.rerun()
        else:
            st.warning("Note is empty.")
                st.markdown("#### Notes log")
    for n in notes[:20]:
        created = n.get("created_at", "")

        if created:
            dt_utc = datetime.fromisoformat(created.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone()
            created_short = dt_local.strftime("%d-%m-%Y %H:%M")
        else:
            created_short = ""

        nt = n.get("note_type", "Note")
        stg = n.get("stage", "")
        header = f"{n['note_date']}  ·  {created_short}  ·  {nt}  ·  {stg}"

        with st.expander(
            f"{header} — {n['content'][:60]}{'…' if len(n['content'])>60 else ''}",
            expanded=False
        ):
            st.write(n["content"])

            edit_key = f"edit_{n['id']}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = False

            c_edit, c_del = st.columns([1, 1])

            if c_edit.button("Edit", key=f"btn_edit_{n['id']}"):
                st.session_state[edit_key] = True

            if c_del.button("Delete", key=f"btn_del_{n['id']}"):
                delete_note(n["id"])
                st.success("Note deleted.")
                st.rerun()

            if st.session_state[edit_key]:
                new_date = st.date_input(
                    "Note date",
                    value=date.fromisoformat(n["note_date"]),
                    key=f"nd_{n['id']}"
                )

                new_type = st.selectbox(
                    "Type",
                    ["LinkedIn", "Email", "Call", "Meeting", "Internal", "Note"],
                    index=["LinkedIn","Email","Call","Meeting","Internal","Note"].index(
                        n.get("note_type", "Note")
                    ),
                    key=f"nty_{n['id']}"
                )

                new_stage = st.selectbox(
                    "Stage",
                    ["New", "Outreach", "Engaged", "Meeting", "Proposal", "Won", "Lost"],
                    index=["New","Outreach","Engaged","Meeting","Proposal","Won","Lost"].index(
                        n.get("stage", "New")
                    ),
                    key=f"nst_{n['id']}"
                )

                new_text = st.text_area(
                    "Edit note",
                    value=n["content"],
                    height=140,
                    key=f"nt_{n['id']}"
                )

                c_save, c_cancel = st.columns([1, 1])

                if c_save.button("Save changes", key=f"btn_save_{n['id']}"):
                    update_note(n["id"], new_text.strip(), new_date, new_type, new_stage)
                    st.session_state[edit_key] = False
                    st.success("Note updated.")
                    st.rerun()

                if c_cancel.button("Cancel", key=f"btn_cancel_{n['id']}"):
                    st.session_state[edit_key] = False
                    st.rerun()

with c2:
    st.markdown("### Workspace")
    top_tabs = st.tabs(["General", "Attachments / progress", "E-mail", "Characteristics", "Cases"])

    dossier_text = dossier_row.get("dossier") or ""
    stakeholders_text = dossier_row.get("stakeholders") or ""
    messages_text = dossier_row.get("messages") or ""
    scan_text = dossier_row.get("business_scan") or ""

    with top_tabs[0]:
        st.subheader("General")
        dossier_text = st.text_area("Dossier (single source of truth)", value=dossier_text, height=260)
        stakeholders_text = st.text_area("Stakeholders", value=stakeholders_text, height=260)

    with top_tabs[1]:
        st.subheader("Attachments / progress")
        st.info("MVP: notes are your progress log. Later: file attachments + stage updates.")

    with top_tabs[2]:
        st.subheader("E-mail")
        messages_text = st.text_area("Messages (LinkedIn + Email)", value=messages_text, height=320)

    with top_tabs[3]:
        st.subheader("Characteristics")
        st.write(f"Industry: {account.get('industry','')}")
        st.write(f"Segment: {account.get('segment','')}")
        st.write(f"Geography: {account.get('geography','')}")
        st.write(f"Priority: {account.get('priority','')}")
        st.write(f"Status: {account.get('status','')}")
        scan_text = st.text_area("Business scan", value=scan_text, height=260)

    with top_tabs[4]:
        st.markdown("#### Link cases to this account (select 1–5)")
        case_search = st.text_input("Search cases (title/tags)", key="case_search")
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

        st.divider()
        st.markdown("#### Add new case")
        ct = st.text_input("Case title", key="new_case_title")
        ci = st.text_input("Industry", key="new_case_industry")
        tg = st.text_input("Tags (comma-separated)", key="new_case_tags")
        cc = st.text_area("Case content (problem → approach → outcome)", height=120, key="new_case_content")

        if st.button("Add case"):
            if ct.strip() and cc.strip():
                add_case(ct.strip(), ci.strip(), tg.strip(), cc.strip())
                st.success("Case added.")
                st.rerun()
            else:
                st.warning("Title and content are required.")

    st.markdown("### Save")
    if st.button("Save all tabs"):
        save_dossier(acc_id, dossier_text, stakeholders_text, messages_text, scan_text)
        st.success("Saved.")

st.divider()
st.subheader("AI Copy/Paste")

mode = st.selectbox("Generate prompt for", ["Update dossier", "Stakeholders", "Message pack", "Business scan"])
prompt = build_prompt(mode, account, {
    "dossier": dossier_text,
    "stakeholders": stakeholders_text,
    "messages": messages_text,
    "business_scan": scan_text
}, notes, linked_cases)

st.text_area("Prompt (copy this into ChatGPT / your internal AI)", value=prompt, height=240)

st.markdown("#### Paste AI output here and apply")
ai_out = st.text_area("AI output", height=220, key="ai_output")

apply_target = st.selectbox("Apply output to", ["Dossier", "Stakeholders", "Messages", "Business scan"])

if st.button("Apply output"):
    if not ai_out.strip():
        st.warning("AI output is empty.")
    else:
        if apply_target == "Dossier":
            dossier_text = ai_out.strip()
        elif apply_target == "Stakeholders":
            stakeholders_text = ai_out.strip()
        elif apply_target == "Messages":
            messages_text = ai_out.strip()
        else:
            scan_text = ai_out.strip()

        save_dossier(acc_id, dossier_text, stakeholders_text, messages_text, scan_text)
        st.success("Applied and saved.")
        st.rerun()

