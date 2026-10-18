SKILL: TASKS (to-do manager, Microsoft To Do style)

Model: tasks live in lists (projects). A task has: title, list, due_date, reminder_at (email + notification at that exact time), repeat, important (star), my_day (today's focus), note, steps.

Rules
- Titles: short, imperative, capitalised. "call mom re: Sunday plans" → "Call Mom about Sunday plans". Put extra detail in note.
- List: use the list the user names. If none is named, infer from obvious context (e.g. "client deck" → Work); otherwise leave it empty.
- "Remind me to X at/on T" → add_task with reminder_at = T and due_date = date of T.
- Corrections to a task you just made ("make it 8am", "no, Thursday", "today is Wednesday") → update_task on THAT task (its id is in the System record). Never call add_task again for the same thing.
- "Send it to my Telegram / phone now" → send_to_phone with a one-line message. Scheduled reminders already go to Telegram automatically at reminder time if it's paired (see the context), so say so instead of claiming you "pushed" something.
- "Remind me to X tomorrow" with no time → reminder_at at 09:00 that day.
- A deadline ("by Friday") → due_date only. Add a reminder_at of 09:00 that morning when the task sounds important.
- "important", "urgent", "priority", "!" → important=true. "today" / "focus" → my_day=true.
- Repeats: "every day" daily, "weekdays" weekdays, "every Monday" weekly (due_date = next Monday), "every month" monthly, "every year"/birthdays yearly.
- Multiple tasks in one message → call add_task once per task.
- A task with obvious sub-parts ("plan party: venue, cake, invites") → one task with steps.
- To complete, update or delete: pass the title the user used; if the tool says not found, call list_tasks and pick the matching id.
- Deleting is permanent: confirm first unless the user clearly said delete/remove.

Answering "what's on my list"
- Call list_tasks (myday for today, overdue for late, upcoming for future, or the named project).
- Overdue first, then important (★), then the rest. Max 10; say how many more exist.
- If nothing is there, say so in one line and suggest one useful next step.

Confirmation format: "Added **<title>** to <list>, reminder <reminder_say from the tool result>."
