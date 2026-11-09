# Obs4MIPs CVs for ESGF-NG

## Process for updating

- Create a branch with the suffix `cv/` for expected changes to the CV content.
- Create a PR to the `esgvoc_dev` branch when this has been tested locally and changes are acceptable.
- A panel member will take the branch and perform the following:
    - Merge your CV branch into esgvoc_dev.
    - Check a PR has been created to push changes to WCRP-universe (panel-controlled)
    - Check the schedule for merging esgvoc_dev into the main branch for publishing a new set of CVs.
    - Merge `esgvoc_dev` to main and WCRP-universe `esgvoc_dev` to main.
    - Trigger a new version of esgvoc to include the new CV changes.

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