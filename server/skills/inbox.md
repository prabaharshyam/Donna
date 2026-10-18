SKILL: INBOX TRIAGE (extract commitments from one email)

You read ONE email and return JSON {"items": [...]} with the actions the user needs to take. Most emails need nothing: return {"items": []}.

Include ONLY:
- In emails the USER SENT: promises the user made ("I'll send the deck by Friday", "let me check and get back to you", "will share the invoice tomorrow").
- In emails the user RECEIVED: direct requests or questions addressed to the user that need a reply or action ("Can you review the contract by Monday?", "Please confirm your attendance", "Your payment is due on 5 Nov").
- Deadlines, appointments or bills that need action.

Exclude: newsletters, promotions, receipts with nothing to do, FYI updates, automated notifications, things already done, things other people promised to do.

Each item:
- title: short imperative task for the user, naming the person or thing ("Send <person> the <thing>", "Reply to <person> about <topic>", "Pay <provider> bill"), using names that appear in THIS email only.
- due_date: YYYY-MM-DD only if a date or clear relative day is stated ("Friday" → resolve using today's date); otherwise omit.
- reason: one short sentence quoting or paraphrasing the line that creates the commitment.

At most 3 items. Never invent commitments that aren't in the email.
