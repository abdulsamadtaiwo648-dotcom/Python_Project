# solobiz-ads

SoloBiz customization of the [Arcads](https://github.com/arcads-ai/skills) ads
plugin. It is a companion layer: the Arcads plugin still does the generating, and
this plugin tells it who SoloBiz is, what it may claim, who it is for, how it looks,
and which ads to make first.

It doesn't fork the Arcads skills, so Arcads updates keep working.

## What's inside

| Skill | What it does |
|---|---|
| `solobiz-brand` | SoloBiz brand brief: product, audience, approved claims, must-not claims, voice, colours, logo. Replaces the Arcads "research the brand" step. |
| `solobiz-ads` | Playbook: plays by goal, five tested angles, hooks, a UGC script template, static templates, and which Arcads skill to run for each. |

The brief lives in `skills/solobiz-brand/references/brand-brief.md`. Every claim
in it comes from the live product pages. Edit that file when the product, pricing or
positioning changes.

## Install

Requires the Arcads plugin and a connected Arcads account.

In Claude Code, from this repository:

```
/plugin marketplace add ./
/plugin install solobiz-ads@solobiz
```

The repository's `.claude/settings.json` also registers the `solobiz` marketplace
from GitHub and enables the plugin, so teammates are offered it automatically once
this is on the default branch.

## Use

- "Make a SoloBiz launch set for Meta"
- "Clone this competitor hook for SoloBiz"
- "Turn our dashboard screenshot into a Reel"
- "Write 5 more hooks for the 'Who owe you?' angle"
