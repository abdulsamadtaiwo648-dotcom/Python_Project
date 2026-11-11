---
name: solobiz-ads
description: SoloBiz ad playbook on top of the Arcads plugin. Ready-made angles, hooks, scripts and format choices for SoloBiz (pocket CFO for independent vendors in Nigeria), and which Arcads skill to run for each. Use when the user asks to make SoloBiz ads, a SoloBiz campaign, UGC, statics, hooks, a launch set, or "ads for my company/app".
---

# SoloBiz ads playbook

Run this with the Arcads plugin. Generation, credits and rendering all happen
through the Arcads MCP tools; this skill decides what to make.

## Before anything

1. Load the `solobiz-brand` skill and read its `references/brand-brief.md`. It is
   the brand brief for every Arcads skill in this session.
2. Ask one question only if the goal isn't clear: "Is this to launch and find a
   first winning angle, to refresh ads that are tiring, or for a specific channel
   (Meta, TikTok, WhatsApp Status)?"
3. Then pick the play from the table below and say it back in one line.

## Plays

| Goal | Play | Arcads skill |
|---|---|---|
| No ads yet / launch | Starter set: 1 static (angle A) + 1 UGC video (angle B). Scale whichever wins. | `arcads:ads` |
| Competitor or viral ad to copy | Rebuild the mechanic with a phone showing SoloBiz | `arcads:clone-hook`, `arcads:clone-static-ad`, `arcads:viral-clone` |
| Turn an existing static into Reels | Reveal the dashboard cards one by one | `arcads:static-to-motion` |
| Explainer | "Where did my money go?" paper-collage explainer | `arcads:animated-ad` |
| Brand / story spot | A market trader's day, SoloBiz as the turning point | `arcads:cinematic-ads` (real-life drama) |
| Ads tiring | New hooks on the winning body | `arcads:ads` (hook multiplication) |
| Find what's working | Small-business finance apps, country NG | `arcads:spy-competitor-ads` |

## Angles (all built from approved claims)

**A. "Who owe you?"** — money stuck with customers who bought on credit.
Proof: record the amount paid and the balance still due; see outstanding balances.

**B. "Busy all day, but where's the profit?"** — sales feel good, but costs eat it.
Proof: track expenses by category next to sales; see net cash flow for any period.

**C. "The notebook is gone."** — rain, a lost exercise book, a missing page.
Proof: records live in SoloBiz on your phone; add it to your home screen.

**D. "Look like a real business."** — send a proper receipt, share a store link.
Proof: shareable receipts with your business details; storefront with WhatsApp and Call buttons.

**E. "You're not on your own."** — community.
Proof: the Floor: anonymous weekly check-ins, Sabi-Plug supplier requests and Street
Wisdom tips from vendors in your city and category.

Default order for testing: A, B, D, C, E.

## Hooks (first 2 seconds)

- "Customer don buy on credit… you remember how much?"
- "You sold all day. How much did you actually make?"
- "If your sales book enter water today, wetin remain?"
- "Stop writing receipts by hand."
- "Your stall has a website now." (storefront)
- "3 things I track every evening before I lock my shop."

## UGC script template (20–30 s, 9:16)

1. **Hook** (0–2 s): one hook from above, said to camera at the stall or counter.
2. **Problem** (2–8 s): one specific moment (a customer saying "I paid you last week").
3. **Show** (8–20 s): phone close-up, record the sale with the balance due, the
   "Sale saved · Receipt ready to share" toast, the summary cards.
4. **Payoff** (20–25 s): "Now I know where I stand."
5. **CTA** (25–30 s): "Create your SoloBiz account. Add it to your home screen."

Actor: Nigerian vendor, 22–45, everyday clothes, real market or shop setting.
Voice: Nigerian English with light Pidgin. Captions in English.

## Static ad templates (4:5 and 1:1)

- **Phone hero:** phone showing the summary cards on an indigo (`#4F46E5`) or canvas
  (`#F8FAFC`) background. Headline: "Track sales and expenses. Know where you stand."
- **Before / after:** a messy notebook with crossed-out figures vs. the SoloBiz
  dashboard. Headline: "From notebook to know-where-you-stand."
- **Receipt:** a shared receipt in a WhatsApp-style chat. Headline: "Send a proper
  receipt in seconds." Don't use WhatsApp's logo or trademarked UI exactly; keep it generic.
- **Who owes you:** a list of names with green "paid" and red "balance" tags.
  Headline: "Know who still owes you."

Text rendering on statics: use `gpt-image-2` (precise text). Add the logo at the edit.

## Quality check before delivery

- Every claim maps to a row in "Approved claims".
- No price, user count, rating, testimonial or security claim.
- Money shown as ₦ and labelled sample/illustrative if not from real data.
- Colours and type match the brief; logo not redrawn.
- Setting and people read as Nigerian vendors, not a corporate office.
