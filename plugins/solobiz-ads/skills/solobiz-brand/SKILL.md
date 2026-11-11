---
name: solobiz-brand
description: SoloBiz brand brief for ad work. Load it before any Arcads skill (arcads:ads, clone-static-ad, clone-hook, viral-clone, static-to-motion, animated-ad, pixar-ad, cinematic-ads, media-router, spy-competitor-ads) runs for SoloBiz, and whenever someone asks for SoloBiz ads, creatives, hooks, scripts, captions or marketing copy. It replaces the Arcads "research the brand" step with the approved SoloBiz brief, claims, audience, voice and colours.
---

# SoloBiz brand layer for Arcads

The Arcads skills start every job by researching the brand's website and writing a
brand brief. For SoloBiz, skip that research. Read
`references/brand-brief.md` and use it as the brief.

## How to apply it

1. Read `references/brand-brief.md` in full before the first generation of the session.
2. When an Arcads skill asks for its brand brief, give a short summary of this one
   (one line on the product, the audience, 2–3 approved claims, the must-not list)
   and confirm it with the user in one line. Don't fetch the website unless the user
   says the brief is out of date.
3. **Claims:** use only the "Approved claims" table. If the user asks for a claim
   that is not in it (price, user numbers, a testimonial, security wording), say it
   isn't in the approved brief and ask them to confirm it and add it to the file first.
4. **Product in Arcads:** use the Arcads product named "SoloBiz". If it doesn't exist,
   ask the user to add it (name SoloBiz, website solobiz.dev, logo from
   `references/logo.svg`) before generating.
5. **Visuals:** pass the colour tokens and look from the brief into image and video
   prompts. Keep the logo and any on-screen text for the edit stage (overlay), not
   inside the generated frame.
6. **Product shots:** SoloBiz is software. The "product" in clone and swap skills is
   a phone showing the SoloBiz dashboard or a shared receipt. Ask the user for real
   screenshots; if none, ask before using the sample-data mockup and keep its
   SAMPLE DATA label.
7. **Competitor research:** with `arcads:spy-competitor-ads`, search the Meta Ad
   Library in Nigeria (country NG) for bookkeeping, sales-tracking, inventory and
   POS apps for small businesses. Use what you find for mechanics only, never
   another brand's assets, claims or actors.

For angles, scripts and format presets, use the `solobiz-ads` skill.
