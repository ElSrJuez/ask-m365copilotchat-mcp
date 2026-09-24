# PPT Annotator

## Purpose

The PPT Annotator is a local Python utility for reviewing one or more PowerPoint files and enriching each slide's speaker notes with grounded, high-value context.

It should:

- read the current notes for each slide
- preserve existing notes rather than rewrite them
- use Ask M365 Copilot Chat MCP plus a reusable context prompt helper to suggest missing details
- append only additive, relevant notes that improve presenter readiness and knowledge transfer

## Intended Outcome

Given a presentation and organizational context, the tool should iteratively produce a copy of the deck with stronger speaker notes, especially where the slide content is terse, acronym-heavy, or assumes project background.

Examples of useful additions:

- acronym expansion
- who is who
- background assumptions the audience may need
- dependencies and blockers
- risks, decisions, and open questions
- owners, timelines, and next steps when they are clearly supported by the material

The tool should not invent facts, restate the slide verbatim, or duplicate what is already in the notes.

## Proposed Implementation Shape

Use Python on Windows with PowerPoint automation so the script can read and write slide notes in the actual `.pptx` file workflow.

Suggested approach:

- use `win32com.client` to open PowerPoint, inspect slides, and update notes text
- use `.env` values to locate input decks, select files, and supply shared prompt context
- call the Ask M365 Copilot bridge to generate note-enrichment suggestions per slide
- write output decks to a temp/output folder instead of overwriting the source by default

## Menu Loop

The first version can be menu-driven.

Suggested actions:

1. Load candidate PowerPoint files from `INPUT_PPT_PATH` using `FILE_SELECTION`
2. Choose a file to process
3. Preview slide titles and existing note length
4. Run annotation for one slide, a range of slides, or the whole deck
5. Review generated note additions before save
6. Save an annotated copy to `TEMP_PATH`

## Configuration

Current config comes from `.env`.

- `INPUT_PPT_PATH`: folder containing source presentations
- `FILE_SELECTION`: file glob, for example `*.PPTX`
- `CONTEXT_PROMPT_HELPER`: shared organizational guidance for note enrichment
- `TEMP_PATH`: output or working folder for annotated copies

## Prompt Contract

For each slide, the model input should include:

- presentation filename
- slide number
- slide title if present
- visible slide text if extractable
- existing speaker notes
- shared `CONTEXT_PROMPT_HELPER`

Expected model behavior:

- preserve the meaning of existing notes
- return only additive note content or a no-change result
- avoid duplication
- stay concise and factual
- explicitly avoid unsupported claims

## First Acceptance Criteria

An initial attempt is successful if it can:

1. list matching `.pptx` files from the configured folder
2. open a chosen deck in PowerPoint via Python
3. read existing notes for each slide
4. generate a candidate additive note block for at least one slide
5. save an annotated copy without damaging the source deck

## Immediate Next Build Step

The next concrete artifact should be a small Python script that:

- loads `.env`
- lists matching decks
- opens one deck with `win32com`
- prints slide numbers, titles, and current notes

That gives a safe first checkpoint before wiring in the Copilot prompt-and-append loop.