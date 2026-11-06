# AGENTS.md — obs4MIPs CVs + QA/QC tool

Guidance for LLM coding agents working on this project. It covers two sibling repos that
must be changed together:

| Repo | Local path | Role |
|---|---|---|
| `obs4MIPs_CVs` | `~/Desktop/repos/obs4MIPs_CVs` | **Source of truth.** Controlled vocabularies (CVs), data reference syntax (DRS), and global-attribute definitions. Consumed by `WCRP-UNIVERSE` / `esgvoc`. |
| `cc-plugin-obs4mips` | `~/Desktop/repos/cc-plugin-obs4mips` | QA/QC tool: an IOOS `compliance-checker` plugin that validates NetCDF files against the Obs4MIPs Data Specifications (ODS). |

The ODS publication (`Obs4MIPs_Data_Specifications_2.6.1.pdf`) is the human-readable spec.
It defines global attributes (Table 1), the DRS, the file-name template, and the
directory template.

## The one rule that matters

**Information about ODS lives in the CVs repo. The QA/QC tool reads it and does not
restate it.**

When you are about to write an ODS fact into QA/QC code (an attribute name, a
requirement level, a separator, a regex, a DRS part list, a CV table name, a list of
allowed values), stop and put it in the CVs repo instead. Then make the tool read it.
Hard-coded ODS facts in QA/QC code are the main thing this project is trying to remove.

What stays in QA/QC code:
- `cv_strictness` (error vs. warn): a tool policy, not an ODS rule.
- Algorithms: comparing attributes to the data in the file, cross-file checks
  (uncertainty and external-variable companion files), parsing time coordinates.
- Python validators for formats a regex cannot express (e.g. UUID validity). Select them
  by name from the CV-side data, never by hard-coding the attribute.

## Where things live in `obs4MIPs_CVs`

- `global_attributes.json` — **on branch `global-json`, not merged.** Master definition of
  every global attribute (schema: `global_attributes_schema.json`): `description`, `dtype`
  (`string`/`boolean`), `separator`, `requirement`, `conditional`, `cv` (table and key), `rc`
  (registered content), `introduced`, `notes`. A generator script will derive the ODS Table 1
  and DRS from it; the QA/QC specs loader will read it.
  - `requirement`: `required` | `recommended` | `optional`. ODS Table 1: "always" is
    required, "encouraged" is recommended, "optional" is optional.
  - `conditional`: `null`, or `{"requirement": <higher level>, "when": "<python expr>"}`
    which raises the level when the expression is true. `when` may only use attribute
    names, quoted string constants, `==`/`!=`, `and`/`or`/`not` (tested). esgvoc cannot
    express conditions, so `attr_specs.yaml` `is_required` is true only for
    `requirement == "required"`.
- `<attribute_name>/` directories — one per CV-backed attribute. Each has a
  `000_context.jsonld` and one `<term>.json` per term. Some directories hold a single
  `regex` term, not enumerated values (e.g. `tracking_id`, `references`,
  `processing_code_location`, `title`). A directory name is **not** always equal to the
  term `type` (`source_id/` → `source`, `institution_id/` → `organisation`, `grid_label/` →
  `grid`, `source_type/` → `obs_type`, `variable_id/` → `variable`). Check an existing term
  before assuming.
- `attr_specs.yaml`, `catalog_specs.yaml`, `drs_specs.yaml`, `project_specs.yaml`,
  `esgvoc_manifest.yaml` — read by `esgvoc` / WCRP-UNIVERSE. `drs_specs.yaml` already
  encodes the directory, file-name and dataset-id part lists.
- `_scripts/` — one-off generators for some CV directories. Read a script before
  hand-editing the files it generates; edits may be overwritten.
- `tests/` — strict pytest tests for `global_attributes.json` (schema in `global_attributes_schema.json`, conditions, CV directories, YAML agreement). No known-issue lists or xfails: failures are real data problems to fix.
- `.github/workflows/ci.yml` — runs `esgvoc admin validate --schema-only .` on push (Python 3.12).

### WCRP-UNIVERSE / esgvoc constraints (verified against esgvoc 7.2.0, 2026-11-04)

Verified by reading the `esgvoc` source and running it. Re-check if the `esgvoc` version
changes (this repo's `pyproject.toml` says `>=5.0.1`; CI installs the latest).

- **CI's `esgvoc admin validate --schema-only .` is weak.** It only checks that
  `esgvoc_manifest.yaml` has `project`, `cv_version`, `universe_version` and that every
  `*.json` under the repo (recursively) parses. Passing it says nothing about the YAMLs,
  term fields, or links to the universe. `global_attributes.json` passes it today.
- **Only these root files are read by the DB build:** `project_specs.yaml` (needs
  `project_id`), `drs_specs.yaml`, `catalog_specs.yaml`, `attr_specs.yaml`, and every
  subdirectory containing `000_context.jsonld`. Any other root file (such as
  `global_attributes.json`) or directory is ignored, not an error.
- **Extra fields are allowed.** Term data descriptors and `ProjectSpecs` use pydantic
  `extra="allow"`. Unknown keys on a term JSON survive into the DB. Unknown keys in
  `attr_specs.yaml` entries or `drs_specs.yaml` are silently ignored (not stored). So
  new data for the QA/QC tool can go in term JSONs, but not in the YAML spec entries.
- **Term kinds:** a term with a `regex` key is a pattern term; one with `parts` is a
  composite term; otherwise plain. `id` and `type` are required; `drs_name` should be
  unique within a collection (duplicates are warned about).
- **Terms merge with the universe.** `@context` in `000_context.jsonld` links the
  collection to a universe data descriptor (via `@base`); term `id`s are resolved against
  universe files and project fields override universe fields. That is why directory name
  ≠ `type`.
- **A full build is the real test.** Run (needs a WCRP-universe checkout):
  `esgvoc admin build -p . -u <WCRP-universe checkout> --project-id obs4mips --cv-version dev --universe-version dev -o out.db`
  The CVs have not been merged into the universe. Team PR
  `WCRP-CMIP/WCRP-universe#332` ("Added ods 2.6.1") adds the universe terms they link to
  (fetch with `git fetch origin pull/332/head`). Against universe `esgvoc_dev` the build
  fails on 348 terms (missing universe files); against PR 332 it now fails on 1: the
  `license` term that links to a missing universe file `regex/cc_by-sa_4.0.json`. `manifest` says `universe_version: 1.0.19`, but the
  universe's only git tag is `v1.0.27`; it should be built against the latest universe.
- **Term file names must be lowercase** (esgvoc `project_ingestion.py`; the term is
  skipped otherwise, and `esgvoc admin validate --schema-only` does not notice). All term
  files are now lowercase (renamed with `git mv`, contents byte-identical).
  `test_cv_term_file_names_are_lowercase` enforces it. Keep `drs_name` in the original case;
  only the *file name* must be lowercase. Never add term files with capitals.
- **`attr_specs.yaml` keys:** esgvoc reads `source_collection`, `field_name`,
  `source_collection_key`, `value_type`, `is_required`. `specific_key` is **silently
  ignored** (use `source_collection_key`). `source_collection: null` (with `field_name`)
  means a free-text attribute that `ncattvalid` does not check against a CV. Keep each
  entry's (collection, key) equal to `cv` in `global_attributes.json` (tested).
- **Regexes in CVs (important):** `regex` on a term makes it a *pattern term*, and
  `valid_term_in_collection` then matches values against the regex (`re.match`) instead
  of `drs_name`. Never add `regex` to terms of an enumerated collection (`source_id`,
  `site_id`, `variable_id`, `institution_id`...): it would turn them into pattern terms
  and drop membership checking. A lone pattern term added to an enumerated collection
  would accept any matching string. Pattern terms are only for collections that are
  entirely patterns (`tracking_id`, `references`, `title`, `variant_label`). A new pattern
  term of `type: regex` also needs its counterpart file in the universe's `regex/`.
- **Project terms override universe terms field by field**, including with `""`. Nothing
  in esgvoc ingestion rejects empty strings; the 122 empty `variable_id` stubs also exist
  identically in universe PR 332, but they can never match a real value. **Decision: keep them.**
- **YAML specs are validated against esgvoc's models** by
  `test_yaml_specs_validate_against_esgvoc_models` (`attr_specs.yaml`, `drs_specs.yaml`,
  `catalog_specs.yaml`). `catalog_specs.yaml` needs `catalog_properties.regex_title`.
  `test_catalog_regex_id_matches_dataset_id_drs` keeps `regex_id`/`regex_title` consistent with
  the `dataset_id` parts in `drs_specs.yaml`.
- **DRS decision (issue #7, `WCRP-ESMO/obs4MIPs_CVs`, still open):** the ODS 2.6.1 directory
  template uses `nominal_resolution`, but published data uses `grid_label`; the ODS is
  considered to have a typo. `drs_specs.yaml` (from dwest77's commit `05676d9`) now uses
  `<activity_id>/<institution_id>/<source_id>/<frequency>/<variable_id>/<grid_label>/<version>`
  for the directory and `activity_id.institution_id.source_id.frequency.variable_id.grid_label.version`
  for the dataset id. `nominal_resolution` stays a global attribute and catalog property.
- `esgvoc ncattvalid <project> [attr] [value]` already validates NetCDF global attributes
  against a project's CVs. It overlaps with the QA/QC tool; check what it does before
  re-implementing CV-membership logic.

Before adding a field to a YAML, run the model check above; before adding to a term JSON
or context, run the build if possible. If you cannot, say the change is unverified.

## Where things live in `cc-plugin-obs4mips`

- `cc_plugin_obs4mips/specs/_base.py` — `AttrSpec` frozen dataclass (name, dtype, rc,
  requirement, required_if, cv, cv_strictness, format_check, format_hint) and
  `derive_global_attr_specs()` for deriving a new ODS version's specs from the old.
- `cc_plugin_obs4mips/specs/ods_2_6_1.py` — **currently hard-coded** `GLOBAL_ATTR_SPECS`
  plus format validators and conditional-requirement predicates. Migration target.
- `cc_plugin_obs4mips/checks/_base.py` — version-independent checks driven by specs
  (presence, format, CV membership).
- `cc_plugin_obs4mips/checks/ods_2_6_1.py` — version-specific logic checks (file name,
  directory, source_id derivation, site consistency, anomaly naming, and stubs for
  aux_uncertainty / conventions / external_variables).
- `cc_plugin_obs4mips/cv.py` — loads packaged CV snapshots from `cv_data/<ods_version>/`.
- `cv_sources.json` + `scripts/sync_cvs.py` — pin a CVs commit and generate `cv_data/`.
  **`cv_data/` is generated. Never edit it by hand.**
- `tests/` — pytest; `tests/data/good_obs4mips.cdl` is the reference-good file.

Specs vs. checks: a **spec** is declarative per-attribute data. A **check** is logic
that needs the dataset or several attributes.

## Commands

CVs repo (Python ≥ 3.12; no dev dependencies are declared yet):
```bash
esgvoc admin validate --schema-only .     # what CI runs; must pass
python -m pip install -r tests/requirements.txt && python -m pytest tests -q
```

QA/QC repo (supports Python ≥ 3.10; CI uses 3.10, so no 3.11+-only syntax or stdlib):
```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run python scripts/sync_cvs.py --check # fails if cv_data/ is stale vs. the pinned CVs ref
```

## Regexes and new CVs (project decisions)

- **No regexes in `global_attributes.json`** (the schema forbids `chars`). Pattern CVs
  (`tracking_id`, `references`, `title`, `variant_label`) carry their own `regex` terms; use
  those. Every other format/character rule (e.g. allowed characters in `source_id`,
  the bare-DOI form) is enforced in the QA/QC tool, kept in **one place** (`specs/`), not
  spread across files. This is the one exception to "don't hard-code ODS facts in the tool".
- **Do not add new CV collections or pattern terms on your own.** Anything shared must
  exist in WCRP-universe. Request the addition there, and first confirm no equivalent
  term already exists in the universe.
- **`dtype` is only `string` or `boolean`** (matching esgvoc's `value_type`). Date and URL
  formats (e.g. ISO 8601 `creation_date`, `processing_code_location`) are checked by the
  QA/QC tool, not described in `global_attributes.json`.
- `source_label` and `source_version_number` are parts of a `source_id` `drs_name`
  (e.g. `20CR-V3` = `20CR` + `V3`), so neither has a CV; both are free text in
  `attr_specs.yaml`. Their link to `source_id` is a QA/QC *check*, not a CV.

## Registered content (RC) is dangerous to change

Registered content is the verbatim text of CV terms (e.g. `drs_name` and `description` in
`institution_id`, `source_id`, `variable_id`; see `rc: "yes"` in `global_attributes.json`).
Data providers copy it **character for character** into their NetCDF files and upload to
ESGF. If a CV term is edited, even a trailing period, capitalization or whitespace, it
stops matching what is already on ESGF and validators will start failing.

- **Never "fix", normalize, re-punctuate, re-case or trim registered content**, even if it
  looks like a typo or differs from another source (such as the PCMDI
  `obs4MIPs-cmor-tables` JSON). These tables were entered by hand, so no source is known
  to be the truth. Report the difference to the user instead.
- Adding, removing or renaming a term is also a registered-content change. Only do it
  when the user explicitly asks, and say what will be affected.
- Generated or bulk edits (scripts in `_scripts/`, formatters, `json.dump` round-trips)
  must not alter term values. Compare before and after.

## Working agreements

1. **Change the CVs repo first, then the tool.** A tool change that needs new ODS data
   should be preceded by (or paired with) the CVs-side change. Say which pinned CVs
   ref (`cv_sources.json`) the tool change depends on.
2. **Don't create a second copy of a fact.** `global_attributes.json`, the YAMLs, the
   CV term files, `cv_sources.json` and `specs/ods_2_6_1.py` already overlap and have
   drifted (see "Known sharp edges" below). If two places must both hold a fact, add a test
   that fails when they disagree.
3. **Characterize before you migrate.** Before replacing hard-coded behavior with
   data-driven behavior, write a test that captures the current behavior, then show
   the new path produces the same result, or list every intentional difference.
4. **Ambiguous ODS wording is a question for the user.** The ODS PDF and the examples
   disagree in places (e.g. `data_specs_version`, `grid_label` for sites). Don't pick
   silently; surface it, record the decision in the `notes` field or a code comment,
   and add a test.
5. **JSON hygiene for `global_attributes.json`:** absent value is `null`, never `""`;
   descriptions don't end in a period; keys in a consistent order; one definition of
   each concept (e.g. one way to express "regex"). Put new conventions in the test
   suite so they hold in future.
6. **Run the checks you touch.** CVs: the esgvoc validator and the tests. QA/QC: pytest,
   ruff, and `sync_cvs.py --check`. Report failures with the output. Do not claim a
   check passed if you didn't run it.
7. **Version vocabulary:** `ods_version` (spec release, e.g. 2.6.1), `data_specs_version`
   (a *global attribute* whose CV holds the CVs-repo tag), and the pinned CVs `ref` in
   `cv_sources.json` are three different things. Don't conflate them.
8. **Git:** don't commit, push or open PRs unless asked. QA/QC commits use conventional
   prefixes (`feat:`, `fix:`, `docs:`, `ci:`, `debug:`). Only stage files you changed.
9. **Scope:** don't refactor unrelated CV directories or regenerate big CV sets
   (`variable_id`, `site_id`, `source_id`, `region`) unless asked.

## Known sharp edges (as of 2026-11-04)

- QA/QC `checks/ods_2_6_1.py` has uncommitted edits that removed `_FILENAME_COMPONENTS`,
  `_DIRECTORY_COMPONENTS` and `_DIRECTORY_TEMPLATE` but the file still uses them, so
  `check_filename` and `check_directory_structure` will raise `NameError`. This looks
  like a mid-refactor toward reading the DRS from `drs_specs.yaml`.
- **Decision: `realm` is single-valued** (no separator; `value_type: string`). The QA/QC tool
  still splits `realm` on whitespace in `checks/_base.py`; that must be removed.
- Separator and multi-value handling disagrees across `global_attributes.json`,
  `attr_specs.yaml` (`string_array`) and `checks/_base.py` (hard-coded split for
  `Conventions`, `activity_id`, `realm`, `region`).
- `sync_cvs.py` `value_field` choices (`cv_sources.json`) disagree with `cv.key` in
  `global_attributes.json` for some tables (e.g. `variable_id`: `id` vs `drs_name`).
- `variant_info`: the JSON condition is `variant_label != institution_id` (recommended),
  but the QA/QC tool's `variant_is_not_be` exempts any label equal to or ending in `-BE`
  (ODS note 15). The grammar cannot express "ends with"; reconcile when migrating the tool.
