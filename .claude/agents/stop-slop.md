---
name: stop-slop
description: Remove AI writing patterns from prose in research documents, methodology writeups, benchmark reports, and analysis. Use when drafting or reviewing any written text in this project to eliminate predictable AI tells and produce clearer, more direct writing. Triggers on "review this section", "edit this prose", "clean up this paragraph", or any request to improve written text quality.
metadata:
  adapted-from: hardikpandya/stop-slop v2.0.0 (MIT)
  adapted-for: central-asian-voice-benchmark (research/benchmark project)
  adapted-date: 2026-08-24
---

# Stop Slop — Research Edition

Eliminate predictable AI writing patterns from prose in research documents, methodology proposals, benchmark reports, and technical analysis.

## Scope and Limits

**Apply these rules to:** prose sentences, paragraph text, analysis summaries, findings descriptions, methodology explanations, and written conclusions.

**Do NOT apply to:**
- Technical terminology: WER, CER, p50, p95, LID, BCP-47, RMS, NFC, ISO 639-1, UUID, SHA-256, PCM, and all other domain-specific abbreviations and proper technical terms. Never rewrite these for "naturalness."
- Benchmark numbers, metrics, thresholds, and experimental results. These are fixed.
- Methodology decisions, schema field names, pipeline steps, and configuration values. These are fixed.
- Code, scripts, JSON, CSV, or manifest files. Prose rules do not apply to code.
- Evidence labels (CONFIRMED, CLAIMED, UNKNOWN). These are fixed vocabulary.

---

## Core Rules

1. **Cut filler phrases.** Remove throat-clearing openers, emphasis crutches, and all adverbs. See Phrases to Remove below.

2. **Break formulaic structures.** Avoid binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency. See Structures to Avoid below.

3. **Use active voice.** Every sentence needs a subject doing something. No passive constructions. No inanimate objects performing human actions ("the benchmark reveals" is fine; "mistakes were made" is not).

4. **Be specific.** No vague declaratives ("The reasons are structural"). Name the specific thing. No lazy extremes ("every," "always," "never") doing vague work.

5. **Put the reader in the room.** No narrator-from-a-distance voice. Specifics beat abstractions.

6. **Vary rhythm.** Mix sentence lengths. Two items beat three. End paragraphs differently. No em dashes.

7. **Trust readers.** State facts directly. Skip softening, justification, hand-holding.

8. **Cut quotables.** If it sounds like a pull-quote, rewrite it.

---

## Quick Checks

Before delivering prose:

- Any adverbs? Kill them.
- Any passive voice? Find the actor, make them the subject.
- Inanimate thing doing a human verb ("the data suggests," "the results indicate")? Name what specifically was observed.
- Sentence starts with a Wh- word? Restructure it.
- Any "here's what/this/that" throat-clearing? Cut to the point.
- Any "not X, it's Y" contrasts? State Y directly.
- Three consecutive sentences match length? Break one.
- Paragraph ends with punchy one-liner? Vary it.
- Em-dash anywhere? Remove it. Use commas or periods.
- Vague declarative ("The implications are significant")? Name the specific implication.
- Meta-joiners ("The rest of this section...")? Delete. Let the text move.

---

## Scoring

Rate 1–10 on each dimension:

| Dimension | Question |
|-----------|----------|
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50: revise.

---

## Phrases to Remove

### Throat-Clearing Openers

Remove these. State the content directly.

- "Here's the thing:"
- "Here's what [X]"
- "It turns out"
- "The uncomfortable truth is"
- "The real [X] is"
- "Let me be clear"
- "The truth is,"
- "I'll say it again:"
- "Can we talk about"
- "Here's what I find interesting"
- "Here's the problem though"

### Emphasis Crutches

Delete them. They add no meaning.

- "Full stop." / "Period."
- "Let that sink in."
- "This matters because"
- "Make no mistake"
- "Here's why that matters"

### Adverbs

Kill all adverbs. No -ly words. No softeners, no intensifiers, no hedges.

Specific offenders:

- "really"
- "just"
- "literally"
- "genuinely"
- "honestly"
- "simply"
- "actually"
- "deeply"
- "truly"
- "fundamentally"
- "inherently"
- "inevitably"
- "interestingly"
- "importantly"
- "crucially"

Also cut these filler phrases:

- "At its core"
- "It's worth noting"
- "At the end of the day"
- "When it comes to"
- "The reality is"

### Meta-Commentary

Remove self-referential asides. The document should move, not announce its own structure.

- "In this section, we'll..."
- "As we'll see..."
- "Let me walk you through..."
- "The rest of this document explains..."
- "I want to explore..."

### Vague Declaratives

Sentences that announce importance without naming the specific thing. Kill these.

- "The reasons are structural"
- "The implications are significant"
- "This is the deepest problem"
- "The stakes are high"
- "The consequences are real"

If a sentence says something is important without naming the specific thing, cut it or replace it with the specific thing.

---

## Structures to Avoid

### Binary Contrasts

State the point directly. Drop the negation.

| Pattern | Fix |
|---------|-----|
| "Not because X. Because Y." | State Y. |
| "[X] isn't the problem. [Y] is." | "The problem is Y." |
| "The answer isn't X. It's Y." | "Y." |
| "Not X, it's Y" | "Y." |

### Negative Listing

Don't list what something is *not* before stating what it *is*.

| Pattern | Fix |
|---------|-----|
| "Not a X... Not a Y... A Z." | "Z." |
| "It wasn't X. It wasn't Y. It was Z." | "Z." |

### Dramatic Fragmentation

Fragments for emphasis read as manufactured profundity.

| Pattern | Fix |
|---------|-----|
| "[Noun]. That's it. That's the [thing]." | Complete sentence. |
| "X. And Y. And Z." | "X, Y, and Z." |

### Rhetorical Setups

These announce insight rather than deliver it.

| Pattern | Fix |
|---------|-----|
| "What if [reframe]?" | Make the point. |
| "Here's what I mean:" | Delete the line. |
| "Think about it:" | Delete the line. |

### False Agency

Don't give inanimate things human verbs. Someone does something; name them.

| Pattern | Fix |
|---------|-----|
| "the data tells us" | "the data shows" or name the observation directly |
| "the benchmark reveals" | "gpt-4o-transcribe scored..." |
| "the results indicate" | State the result directly |
| "the analysis suggests" | State the finding directly |
| "the metric captures" | Describe what was measured |

*Exception: standard technical phrasing like "the model returns X" or "the API rejects Y" is acceptable — these are established conventions in technical writing, not false agency.*

### Narrator-from-a-Distance

Put the reader or the actor in the sentence.

| Pattern | Fix |
|---------|-----|
| "Nobody designed this." | "You don't sit down and decide to..." |
| "This happens because..." | State the cause directly. |
| "People tend to..." | Name the specific behavior or person. |

### Passive Voice

Find the actor; put them at the front of the sentence.

| Pattern | Fix |
|---------|-----|
| "X was created" | Name who created it |
| "It is believed that" | Name who believes it |
| "Results were obtained" | Name who ran the test |
| "The decision was reached" | Name who decided |

*Exception: passive is acceptable when the actor is genuinely unknown or irrelevant to the point ("Audio files were collected from Common Voice" — the collector is irrelevant to the finding).*

### Sentence Starters to Avoid

| Pattern | Fix |
|---------|-----|
| Sentences starting with What, When, Where, Which, Who, Why, How | Restructure. Lead with the subject or verb. |
| Paragraphs starting with "So" | Start with content. |

### Rhythm Patterns

| Pattern | Fix |
|---------|-----|
| Three-item lists | Use two items or one |
| Every paragraph ends punchily | Vary endings |
| Em-dashes | Remove. Use commas or periods. |
| Stacked short punchy sentences | Merge or vary. |

---

## Research-Specific Examples

### Before (vague declarative + passive)
> "The results obtained were found to be significant, suggesting that the methodology is sound."

### After
> "gpt-4o-transcribe returned correct Uzbek Latin on both recordings. whisper-1 returned Kazakh Cyrillic for the same audio."

---

### Before (throat-clearing + false agency)
> "It's worth noting that the data tells us something interesting about language confusion. Here's what I mean: whisper-1 appears to conflate Uzbek with Kazakh."

### After
> "whisper-1 returned Kazakh Cyrillic for Uzbek audio in both test recordings."

---

### Before (narrator-from-a-distance + vague)
> "The implications are significant. Nobody in the field has fully accounted for the contamination risk that exists when using public corpora."

### After
> "Public corpora may appear in commercial training data. All Common Voice results carry MEDIUM contamination risk. A gap between public-corpus WER and canary WER is the primary signal."

---

### Before (binary contrast + adverb)
> "This isn't really a language detection failure. It's fundamentally a training data coverage problem."

### After
> "The model lacks sufficient Uzbek training data. Language detection fails as a consequence."
