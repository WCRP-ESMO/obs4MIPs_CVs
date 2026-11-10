# Obs4MIPs CVs for ESGF-NG

## Catalog Specs Guide

- source_collection: Source CVs used to generate the schema to allow only specific values sourced from this repo.
- catalog_field_name: Name as it appears in the catalog schema (with <project> as prefix)
- catalog_field_value_type: Type of value to specify in the schema
- is_required: Boolean field to specify if field is required or not.
- source_collection_key: Pull all the values from 'source_collection.key' to use as the specific values, instead of just the ids.

If the source_collection is 'null', no CVs are sourced and any value is allowed.

## Process for updating

- Create a branch with the suffix `cv/` for expected changes to the CV content.
- Create a PR to the `esgvoc_dev` branch when this has been tested locally and changes are acceptable.
- A panel member will take the branch and perform the following:
    - Merge your CV branch into esgvoc_dev.
    - Check a PR has been created to push changes to WCRP-universe (panel-controlled)
    - Check the schedule for merging esgvoc_dev into the main branch for publishing a new set of CVs.
    - Merge `esgvoc_dev` to main and WCRP-universe `esgvoc_dev` to main.
    - Trigger a new version of esgvoc to include the new CV changes.

## CI and publication (esgvoc registry)

| Event | Workflow | What happens |
|-------|----------|--------------|
| PR to `esgvoc_dev` | `esgvoc-dev.yml` | Build the DB against WCRP-universe `esgvoc_dev`, validate it, generate the STAC schema (DB and schema uploaded as workflow artifact) |
| Merge to `esgvoc_dev` | `esgvoc-dev.yml` | Same check, then print the command publishing `obs4mips@dev-latest` to [esgvoc_registry](https://github.com/WCRP-CMIP/esgvoc_registry) |
| PR to `main` | `test-prod.yml` | Same check against WCRP-universe `main`, plus a release preview comment (suggested version bump and changelog) |
| Merge to `main` | `publish-prod.yml` | Open a `chore: update manifest to X.Y.Z` PR |
| Merge of the manifest PR | `publish-prod.yml` | Print the command publishing `obs4mips@X.Y.Z` (the `cv_version` of the manifest) to the registry |
| Manual | `publish-prod-universe-changed.yml` | Open a manifest PR to rebuild obs4mips with a new universe release |

`esgvoc-dev.yml` can also be run by hand against another universe branch (e.g. a WCRP-universe PR branch).

Publication is manual by design: run the printed `gh workflow run publish.yml ...` command
(job log and summary); it needs the right to run workflows on `WCRP-CMIP/esgvoc_registry`.

## Local testing
Test changes locally with obs4MIPs_CVs, esgvoc and WCRP-Universe. This may also include using `esg-publisher` to verify STAC record creation success before new CVs are published to ESGF-NG.

### Build DB Locally

https://esgf.github.io/esgf-vocab/how_to/configuration.html#advanced-using-locally-built-databases

### Steps

esgvoc admin build --project-path ./obs4MIPs_CVs/ --universe-path ./WCRP-universe/ --project-id obs4mips --cv-version dev --universe-version dev --output obs4mips.db

esgvoc admin install obs4mips ./obs4mips.db --name my-experiment

esgvoc use obs4mips@my-experiment

esgvoc admin validate obs4mips.db

ncdump -h <file> | esgvoc ncattvalid obs4mips

## Notes for reviewer

The following fields are not included in the STAC schema but are included in attribute validation:
- comment
- contact
- creation_date (may interfere with STAC creation date? - also linked to version?)
- dataset contributor
- doi (citation url already included?)
- history
- long_name (variable_long_name as per CF)
- references
- source_data_notes
- source_data_retrieval_date
- source_data_url
- source_version_number
- units_metadata

The following fields are not included in the CV directories currently where they are listed in the CMOR tables:
- required_global_attributes (presumably handled separately to CVs)
- table_id
- site_id
- aux_uncertainty_id
- has_aux_unc

It is unclear how the `aux_uncertainty` fields should be dealt with via the `000_context.jsonld` files as these fields do not exist in the main `WCRP-universe` context at all.