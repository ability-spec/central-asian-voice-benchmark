# Skill Adoption Analysis
## Source: Prepl-product-launch-page / .agent/SKILLS/

**Date:** 2026-08-24
**Status:** Analysis only. No skills imported. Awaiting approval.
**Analyst:** Claude (Sonnet 4.6)

---

## Summary

13 skills were reviewed from the Prepl repository. 12 are tightly coupled to web app development (React, Next.js, Tailwind CSS, GSAP animations, Lottie, Three.js, HyperFrames video rendering, SEO, and conversion copywriting). They assume a frontend product architecture that does not exist in this project and would introduce inappropriate behavioral expectations.

One skill — `stop-slop` — is domain-neutral. It enforces prose quality rules applicable to any written output: research documents, methodology proposals, benchmark reports, analysis findings, and documentation.

**Recommendation:** Adapt `stop-slop` only. Reject all others.

---

## Skill-by-Skill Analysis

| Skill | What it does | Relevant? | Decision | Reason |
|---|---|---|---|---|
| `content-strategy` | Plans marketing content (SEO, traffic, leads, topic clusters, buyer journey) | No | **REJECT** | Entirely marketing/product focused. Assumes a SaaS product, customers, and blog strategy. No research applicability. |
| `copy-editing` | Reviews marketing copy through 7 sweeps (clarity, voice, "so what", proof, specificity, emotion, zero risk) | No | **REJECT** | Framework is built for conversion copywriting (CTAs, trust signals, risk reversals). The prose principles in Sweeps 1–2 overlap with stop-slop but with marketing-specific framing. stop-slop covers the general case better. |
| `copywriting` | Writes marketing copy for landing pages, pricing pages, feature pages | No | **REJECT** | Conversion copywriting for a SaaS product. Entirely irrelevant. |
| `frontend-design` | Creates distinctive frontend interfaces (HTML/CSS/JS, React, Vue) with strong aesthetic direction | No | **REJECT** | No frontend development in this project. Assumes web UI delivery. |
| `gsap` | GSAP animation library reference for HyperFrames video compositions | No | **REJECT** | HyperFrames-specific. No animation, video, or browser rendering in this project. |
| `lottie` | Lottie/dotLottie adapter patterns for HyperFrames | No | **REJECT** | HyperFrames-specific. Same reason as `gsap`. |
| `make-interfaces-feel-better` | UI polish principles (border radius, transitions, font smoothing, hit areas, micro-interactions) | No | **REJECT** | Entirely UI/frontend. No interface work in this project. |
| `seo-audit` | Technical and on-page SEO auditing for websites | No | **REJECT** | Web-specific. No website, no search ranking concerns. |
| `stop-slop` | Removes AI writing patterns from prose: filler phrases, passive voice, vague declaratives, binary contrasts, false agency, rhythmic predictability | **Yes** | **ADAPT** | Research documents, methodology proposals, benchmark reports, and analysis write-ups all benefit from these rules. The skill is domain-neutral. Needs adaptation to remove marketing-specific content. |
| `tailwind` | Tailwind CSS v4 browser-runtime patterns for HyperFrames | No | **REJECT** | HyperFrames-specific. No CSS, no web output. |
| `three` | Three.js/WebGL patterns for HyperFrames compositions | No | **REJECT** | HyperFrames-specific. No 3D graphics. |
| `vercel-react-best-practices` | 45 React/Next.js performance optimization rules (bundle size, server components, re-render optimization) | No | **REJECT** | React/Next.js-specific. No JavaScript framework in this project. |
| `web-design-guidelines` | Reviews UI code against Vercel's Web Interface Guidelines | No | **REJECT** | Web UI review tool. No UI to review. |

---

## Recommended Adaptation: `stop-slop`

### What the original skill does

Provides rules, checklists, and scored dimensions for removing AI writing patterns from prose. Core rules: cut filler, active voice, be specific, trust readers, vary rhythm, no vague declaratives, no false agency, no binary contrasts.

### Why it applies here

This project produces substantial written output:
- Methodology proposals (`methodology_proposal.md`)
- Benchmark configuration documents (`stt_benchmark_config.md`)
- Research summaries and statistics (`audio_benchmark_statistics.md`, speaker distribution reports)
- Smoke test and pilot reports (`step7_pilot_report.md`, `kazakh_stt_smoke_test.md`)
- Final benchmark reports (`final_benchmark_report.md`)

These documents carry research conclusions. AI-generated prose patterns (passive voice, vague declaratives, throat-clearing openers, false agency) reduce credibility and obscure meaning. The rules apply directly.

### What to strip during adaptation

Remove from the original:
- Business jargon table (Navigate → Handle, Landscape → Situation, etc.) — not present in research writing
- Conversion-specific examples (features vs. benefits, CTA copy)
- References to marketing/product context

Keep:
- All 8 Core Rules
- Quick Checks (all applicable)
- Scoring rubric (Directness, Rhythm, Trust, Authenticity, Density)
- Phrases to Remove: throat-clearing openers, emphasis crutches, adverbs, meta-commentary, vague declaratives
- Structures to Avoid: binary contrasts, passive voice, false agency, narrator-from-a-distance, dramatic fragmentation, rhetorical setups

### Proposed location

```
.agent/SKILLS/stop-slop/SKILL.md
```

This mirrors the source structure. If the project adopts Claude Code's native `.claude/agents/` format instead, the file would move to:

```
.claude/agents/stop-slop.md
```

The `.agent/SKILLS/` path matches the Prepl convention and keeps skills co-located and discoverable. Either location works; the `.claude/agents/` path is Claude Code's native lookup path and is preferred for skills that should be auto-invocable.

---

## Decision Summary

| Category | Skills | Count |
|---|---|---|
| ADAPT | `stop-slop` | 1 |
| REJECT — web/frontend | `frontend-design`, `tailwind`, `make-interfaces-feel-better`, `web-design-guidelines`, `gsap`, `lottie`, `three` | 7 |
| REJECT — marketing/copy | `content-strategy`, `copywriting`, `copy-editing`, `seo-audit` | 4 |
| REJECT — React/Next.js | `vercel-react-best-practices` | 1 |
| **Total reviewed** | | **13** |

---

## What is NOT needed from the Prepl skill set

The Prepl skills notably lack:
- Research methodology discipline
- Data validation and reproducibility
- Python scripting patterns
- Audio processing or NLP tooling
- Structured experiment logging
- Evidence labeling (CONFIRMED / CLAIMED / UNKNOWN)

These gaps are not a problem — they are filled by the project's own `CLAUDE.md` evidence standards, `methodology_proposal.md`, and the configuration documents already in place. No additional Prepl skill would improve any of these.

---

*Awaiting approval before any files are created or modified.*
