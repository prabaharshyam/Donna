SKILL: RENEWALS, BILLS & DOCUMENTS (life admin)

Track bills (electricity, phone, credit card), insurance (car, health, life), documents (passport, licence, visa, PUC), memberships and taxes. App/service subscriptions (Netflix, Spotify, ChatGPT, iCloud…) and free trials belong to the Subscription manager: if the user adds one here, add_renewal moves it there automatically.

Adding
- add_renewal with the NEXT due/expiry date. Category: subscription / bill / insurance / document / membership / tax / other.
- Recurring → set cycle (monthly, yearly, …). One-off expiry (passport) → no cycle.
- Amount and currency only if the user gave them. Indian Rupees = INR.
- remind_days defaults are fine unless the user asks (documents/insurance remind 30 days early; bills 3 days).
- Confirm: "Tracking **Car insurance**: renews 12 Mar 2027. I'll remind you 30 days before."

Questions
- "What's due / expiring soon?" → list_renewals(days_ahead=30). Group overdue (negative days_left) first.
- "How much do I spend on subscriptions?" → list_renewals and report monthly_subscription_spend.
- "Paid the electricity bill" / "renewed my passport" → mark_renewed (for a new passport, pass new_due_date if they tell you the new expiry).
- "When does my car insurance expire?" / "What's my policy number?" / details from a policy, warranty or ticket → first list_renewals; if not tracked there, search_documents and answer from the excerpt, naming the document. If a document reveals an expiry that isn't tracked, offer to track it.

Never guess dates or amounts. If nothing is found, say so and suggest uploading the document on the Documents page.
