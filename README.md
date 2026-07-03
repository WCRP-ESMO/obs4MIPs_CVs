# Obs4MIPs CVs for ESGF-NG

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