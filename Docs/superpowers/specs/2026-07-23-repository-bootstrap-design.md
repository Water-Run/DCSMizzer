# Repository Bootstrap Design

## Scope

Prepare the repository's introductory documentation and local reference-source
layout without implementing DCS mission-generation features.

## README

- Translate `README-zh.md` faithfully into English in `README.md`.
- Preserve the Chinese document's structure, links, example prompt, and informal
  tone.
- In both languages, set the example mission in a summer afternoon while
  retaining the heavy rain, low cloud, and strong wind.
- Make the player MiG-29A flight start cold from a Soviet airbase near East
  Berlin.
- Describe the setting as late-1980s Cold War equipment and atmosphere without
  redundantly excluding R-77 or MICA.

## Ignore Rules

Initialize `.gitignore` for common Python, Lua, editor, operating-system,
temporary, secret, build, and generated-output artifacts.

The `.develope` directory has one tracked explanatory file:
`.develope/README.txt`. All other direct or nested content beneath
`.develope/` is ignored by the parent repository.

## Reference Repositories

Clone the six projects named in the acknowledgements section of
`README-zh.md` into separate child directories under `.develope/`. Keep each
clone intact, including its own `.git` directory, because the parent ignore
rules isolate all clone contents.

The six repositories are:

1. pydcs
2. BriefingRoom for DCS
3. dcs-mission-maker
4. DCS Global Terrain Database
5. DCS Retribution
6. MOOSE

## Verification

- Compare the headings, links, lists, and prompt meaning across both README
  languages.
- Verify `.develope/README.txt` is not ignored.
- Verify a representative cloned file and nested `.git` path are ignored.
- Verify all six clone directories exist and each has a valid `HEAD`.

