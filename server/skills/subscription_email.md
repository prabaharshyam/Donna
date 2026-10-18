You read ONE email and decide whether it is about a paid subscription or free trial the user has, and return JSON.

event, one of:
- trial_started: a free trial began (look for the trial end / first charge date → trial_end).
- charged: a subscription payment succeeded (receipt, invoice, "payment successful", "your membership has been renewed").
- upcoming_charge: a notice before a charge, including Indian bank/UPI **pre-debit notifications** for e-mandates/AutoPay ("₹649 will be debited on 21-10-2026 towards NETFLIX"), and "your plan renews on …" reminders. Put the debit/renewal date in next_date.
- price_change: the service announces a new price (put the NEW amount in amount).
- payment_failed: a payment was declined/failed, or the card on file needs updating.
- cancelled: confirms the subscription was cancelled or will end (put the end date in next_date).
- not_subscription: everything else (one-off purchases, orders, deliveries, OTPs, bank statements, promotions, newsletters, offers to subscribe, someone else's subscription).

Fields:
- service: the brand the user subscribes to, short and clean ("Netflix", "Claude Pro", "iCloud+", "YouTube Premium"). For App Store / Google Play receipts, the app's name, not Apple/Google. For a UPI/bank mandate notice, the merchant named in it.
- plan: plan name if stated ("Premium", "Pro annual").
- amount + currency: the subscription price/charge as a number, ISO currency (INR for ₹/Rs). Omit if not stated.
- date: the charge/event date YYYY-MM-DD (use the email date if the charge date isn't stated).
- next_date / trial_end: YYYY-MM-DD when stated. Dates in Indian emails are usually DD-MM-YYYY or DD/MM/YYYY.
- cycle: monthly / yearly / quarterly / half-yearly / weekly if clear from the email, else "unknown".
- evidence: one short sentence quoting the line that proves it.

Only use facts in the email. Never guess prices or dates. Marketing emails that invite the user to subscribe are not_subscription.
