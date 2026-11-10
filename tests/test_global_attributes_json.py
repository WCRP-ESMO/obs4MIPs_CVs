"""
Tests that keep global_attributes.json consistent now and in the future.

These tests are deliberately strict: there are no lists of "known issues" and no xfail
markers. If the data is wrong, the test fails and says what to fix.

Layers:

1. Structure: the file matches global_attributes_schema.json plus house style rules.
2. Internal consistency: `conditional.when` expressions are real, evaluable Python logic that only
   refers to global attributes; `introduced` <= `ods_version`.
3. Regexes: none in global_attributes.json (pattern CVs hold their own `regex` terms;
   other format rules live in the QA/QC tool).
4. Cross-file consistency: CV directories and keys exist, and attr_specs.yaml /
   drs_specs.yaml agree with this file.

Project decisions encoded here:
- A CV directory named after a global attribute means that attribute's `cv` is not null.
- attr_specs.yaml only describes global attributes: every entry's name must be one, and
  every `source_collection` must be a CV directory.
- `version` and `time_range` are not global attributes but are legitimate DRS parts
  (they are CV directories).
- Empty stub terms (all fields "") are allowed: esgvoc does not reject them.
"""

import ast
import glob
import json
import os
import re

import jsonschema
import pytest
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
ATTR_NAMES = sorted(
    json.load(open(os.path.join(ROOT, "global_attributes.json")))["global_attributes"]
)

ATTR_KEY_ORDER = [
    "description",
    "dtype",
    "separator",
    "requirement",
    "conditional",
    "cv",
    "rc",
    "introduced",
    "notes",
]


# ---- helpers ---------------------------------------------------------------------------


def _ver(s):
    return tuple(int(p) for p in s.split("."))


def _cv_dirs(repo_root):
    return {
        os.path.basename(os.path.dirname(p))
        for p in glob.glob(str(repo_root / "*" / "000_context.jsonld"))
    }


def _terms(repo_root, table):
    out = {}
    for f in sorted(glob.glob(str(repo_root / table / "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out[os.path.basename(f)] = json.load(fh)
    return out


def _strings(obj):
    """Yield every string value anywhere inside a JSON-like object."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


# Conditions are Python expressions over global attribute names, e.g.
#   product == "site-observations" or product == "site-collection"
#   variant_label != institution_id
#   has_aux_unc == "TRUE"
# Allowed: or / and / not, == and != (one comparison at a time), attribute names, string
# and boolean constants. Nothing else (no calls, attribute access, arithmetic, ...).
def condition_problems(expr, attr_names):
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return [f"not valid Python ({e.msg}); quote string values, use '==' not '='"]
    problems = []

    def visit(node):
        if isinstance(node, ast.Expression):
            visit(node.body)
        elif isinstance(node, ast.BoolOp):
            for v in node.values:
                visit(v)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            visit(node.operand)
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1 or not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
                problems.append("only a single '==' or '!=' comparison is allowed")
            for v in [node.left, *node.comparators]:
                visit(v)
        elif isinstance(node, ast.Name):
            if node.id not in attr_names:
                problems.append(
                    f"{node.id!r} is not a global attribute (quote it if it is a value)"
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bool)):
            pass
        else:
            problems.append(f"unsupported syntax: {ast.dump(node)[:60]}")

    visit(tree)
    return problems


def evaluate_condition(expr, values):
    """Evaluate a validated condition; attributes missing from `values` are None."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BoolOp):
            results = [ev(v) for v in node.values]
            return all(results) if isinstance(node.op, ast.And) else any(results)
        if isinstance(node, ast.UnaryOp):
            return not ev(node.operand)
        if isinstance(node, ast.Compare):
            left, right = ev(node.left), ev(node.comparators[0])
            return left == right if isinstance(node.ops[0], ast.Eq) else left != right
        if isinstance(node, ast.Name):
            return values.get(node.id)
        return node.value

    return ev(ast.parse(expr, mode="eval"))


# ---- 1. structure ----------------------------------------------------------------------


def test_matches_json_schema(doc, schema):
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in errors
    )


def test_no_tabs(raw_text):
    assert "\t" not in raw_text, "use spaces, not tabs"


@pytest.mark.parametrize("name", ATTR_NAMES)
def test_attribute_style(name, attrs):
    a = attrs[name]
    keys = list(a)
    expected = [k for k in ATTR_KEY_ORDER if k in a]
    assert keys == expected, f"{name}: keys must be ordered {expected}, got {keys}"
    assert not a["description"].endswith("."), f"{name}: description ends with a period"
    assert a["description"][0].isupper() or a["description"][0] in "'\"", (
        f"{name}: description should start with a capital letter"
    )


def test_introduced_not_after_ods_version(doc, attrs):
    ods = _ver(doc["ods_version"])
    late = {n: a["introduced"] for n, a in attrs.items() if _ver(a["introduced"]) > ods}
    assert not late, (
        f"attributes introduced after ods_version {doc['ods_version']}: {late}"
    )


def test_boolean_attributes_are_single_valued(attrs):
    bad = [
        n
        for n, a in attrs.items()
        if a["dtype"] == "boolean" and a["separator"] is not None
    ]
    assert not bad, f"boolean attributes cannot be multi-valued: {bad}"


# ---- 2. conditions ---------------------------------------------------------------------


LEVEL_RANK = {"optional": 0, "recommended": 1, "required": 2}


@pytest.mark.parametrize("name", ATTR_NAMES)
def test_conditional_requirement_is_valid_logic(name, attrs):
    """
    `requirement` is the unconditional level. `conditional` (or null) raises it when `when`
    is true. `when` must be real Python logic over global attributes (see condition_problems).
    """
    a = attrs[name]
    cond = a["conditional"]
    if cond is None:
        return
    assert LEVEL_RANK[cond["requirement"]] > LEVEL_RANK[a["requirement"]], (
        f"{name}: conditional level {cond['requirement']!r} must be higher than the base "
        f"requirement {a['requirement']!r}"
    )
    problems = condition_problems(cond["when"], set(attrs))
    assert not problems, f"{name}: {cond['when']!r}: " + "; ".join(problems)
    # It must also evaluate to a bool for an arbitrary (here: empty) attribute set.
    assert isinstance(evaluate_condition(cond["when"], {}), bool)


# ---- 3. regexes live in the CV ---------------------------------------------------------


def test_cv_regex_terms_compile(repo_root):
    bad = {}
    for table in sorted(_cv_dirs(repo_root)):
        for fname, term in _terms(repo_root, table).items():
            if "regex" in term:
                try:
                    re.compile(term["regex"])
                except (re.error, TypeError) as e:
                    bad[f"{table}/{fname}"] = str(e)
    assert not bad, bad


def test_no_regexes_in_global_attributes_json(raw_text):
    """
    Regexes are never stored in global_attributes.json. Pattern CVs (tracking_id,
    references, title, variant_label) carry their own `regex` terms; every other
    character/format rule is enforced in the QA/QC tool, in one place.
    """
    assert '"chars"' not in raw_text and '"regex"' not in raw_text
    suspicious = re.findall(r'"[^"\n]*(?:\^|\$|\[\^|\(\?)[^"\n]*"', raw_text)
    assert not suspicious, (
        f"regex-looking strings in global_attributes.json: {suspicious}"
    )


# ---- 4. cross-file consistency ---------------------------------------------------------


def test_cv_tables_exist(attrs, repo_root):
    dirs = _cv_dirs(repo_root)
    missing = {
        n: a["cv"]["table"]
        for n, a in attrs.items()
        if a["cv"] and a["cv"]["table"] not in dirs
    }
    assert not missing, f"cv.table has no directory with 000_context.jsonld: {missing}"


def test_cv_directory_named_after_attribute_means_cv_not_null(attrs, repo_root):
    dirs = _cv_dirs(repo_root)
    bad = sorted(n for n, a in attrs.items() if a["cv"] is None and n in dirs)
    assert not bad, (
        f"CV directory exists but cv is null in global_attributes.json: {bad}"
    )


def test_cv_keys_present_in_non_pattern_terms(attrs, repo_root):
    """Terms with a `regex` are pattern terms and need no value key; all others do."""
    bad = {}
    for name, a in attrs.items():
        cv = a["cv"]
        if not cv or not cv["key"]:
            continue
        lacking = sorted(
            f
            for f, t in _terms(repo_root, cv["table"]).items()
            if "regex" not in t and cv["key"] not in t
        )
        if lacking:
            bad[f"{name} (cv {cv['table']}.{cv['key']})"] = lacking
    assert not bad, f"terms missing the key global_attributes.json points at: {bad}"


def test_cv_term_file_names_are_lowercase(repo_root):
    """
    esgvoc skips any term file whose name is not lowercase at build time
    (project_ingestion.py), but `esgvoc admin validate --schema-only` does not notice.
    Only the *file name* must be lowercase; `drs_name` keeps its original case.
    """
    bad = {}
    for table in sorted(_cv_dirs(repo_root)):
        files = sorted(
            os.path.basename(f) for f in glob.glob(str(repo_root / table / "*.json"))
        )
        upper = [f for f in files if f != f.lower()]
        if upper:
            bad[table] = f"{len(upper)} file(s), e.g. {upper[:3]}"
    assert not bad, f"term file names must be lowercase: {bad}"


@pytest.fixture(scope="module")
def attr_specs(repo_root):
    return yaml.safe_load((repo_root / "attr_specs.yaml").read_text())


@pytest.fixture(scope="module")
def drs_specs(repo_root):
    return yaml.safe_load((repo_root / "drs_specs.yaml").read_text())


def _yaml_name(entry):
    return entry.get("field_name", entry["source_collection"])


def test_attr_specs_only_describes_global_attributes(attrs, attr_specs):
    bad = sorted({_yaml_name(e) for e in attr_specs} - set(attrs))
    assert not bad, f"attr_specs.yaml entries that are not global attributes: {bad}"


def test_attr_specs_source_collections_are_cv_directories(attr_specs, repo_root):
    dirs = _cv_dirs(repo_root)
    # esgvoc: source_collection is the collection that originated the attribute, or null.
    bad = sorted(
        {e["source_collection"] for e in attr_specs if e["source_collection"]} - dirs
    )
    assert not bad, (
        f"attr_specs.yaml source_collection is not a CV directory (use null and set "
        f"field_name for attributes without a CV): {bad}"
    )


def test_every_global_attribute_is_in_attr_specs(attrs, attr_specs):
    missing = sorted(set(attrs) - {_yaml_name(e) for e in attr_specs})
    assert not missing, f"missing from attr_specs.yaml: {missing}"


def test_attr_specs_is_required_agrees(attrs, attr_specs):
    bad = []
    for e in attr_specs:
        name = _yaml_name(e)
        if name in attrs:
            # esgvoc only has a boolean: true means unconditionally required.
            json_required = attrs[name]["requirement"] == "required"
            if e["is_required"] != json_required:
                bad.append(
                    f"{name}: yaml is_required={e['is_required']}, json={json_required}"
                )
    assert not bad, bad


def test_attr_specs_use_only_keys_esgvoc_reads(attr_specs):
    """esgvoc silently ignores unknown keys (e.g. `specific_key`; the real one is `source_collection_key`)."""
    allowed = {
        "source_collection",
        "field_name",
        "source_collection_key",
        "value_type",
        "is_required",
    }
    bad = {
        _yaml_name(e): sorted(set(e) - allowed) for e in attr_specs if set(e) - allowed
    }
    assert not bad, f"attr_specs.yaml keys esgvoc does not read: {bad}"


def test_attr_specs_cv_agrees_with_global_attributes(attrs, attr_specs):
    """The CV (table, key) in attr_specs.yaml must equal `cv` in global_attributes.json.

    JSON `cv: null` <-> YAML `source_collection: null` (free text);
    JSON key null or "drs_name" <-> YAML `source_collection_key` omitted.
    """
    bad = []
    for e in attr_specs:
        name = _yaml_name(e)
        if name not in attrs:
            continue
        cv = attrs[name]["cv"]
        want = (
            (None, None)
            if cv is None
            else (cv["table"], None if cv["key"] in (None, "drs_name") else cv["key"])
        )
        got = (e["source_collection"], e.get("source_collection_key"))
        if got != want:
            bad.append(
                f"{name}: attr_specs.yaml has {got}, global_attributes.json implies {want}"
            )
    assert not bad, bad


def test_drs_parts_are_attributes_or_cv_directories(attrs, drs_specs, repo_root):
    """version and time_range are not global attributes but are CV directories."""
    dirs = _cv_dirs(repo_root)
    bad = sorted(
        {
            f"{kind}:{p['source_collection']}"
            for kind, spec in drs_specs.items()
            for p in spec["parts"]
            if p["source_collection"] not in attrs
            and p["source_collection"] not in dirs
        }
    )
    assert not bad, (
        f"DRS parts that are neither a global attribute nor a CV directory: {bad}"
    )


def test_drs_required_parts_are_required_attributes(attrs, drs_specs):
    bad = []
    for kind, spec in drs_specs.items():
        for p in spec["parts"]:
            a = attrs.get(p["source_collection"])
            if a is None or not p["is_required"]:
                continue
            if a["requirement"] != "required":
                bad.append(
                    f"{kind}: {p['source_collection']} is a required DRS part but its "
                    f"requirement is {a['requirement']!r}"
                )
    assert not bad, bad


def test_every_cv_directory_is_referenced(attrs, repo_root):
    referenced = {a["cv"]["table"] for a in attrs.values() if a["cv"]}
    for fname in ("drs_specs.yaml", "attr_specs.yaml", "catalog_specs.yaml"):
        referenced |= set(
            re.findall(r"source_collection:\s*(\w+)", (repo_root / fname).read_text())
        )
    unreferenced = sorted(_cv_dirs(repo_root) - referenced)
    assert not unreferenced, f"CV directories nothing refers to: {unreferenced}"


def test_yaml_specs_validate_against_esgvoc_models(repo_root):
    """The YAMLs must load with esgvoc's own pydantic models (CI's validator does not check this)."""
    from esgvoc.api.project_specs import (
        AttributeSpecification,
        CatalogSpecification,
        DrsSpecification,
        DrsType,
    )
    from pydantic import TypeAdapter

    def load(name):
        return yaml.safe_load((repo_root / name).read_text())

    TypeAdapter(AttributeSpecification).validate_python(load("attr_specs.yaml"))
    TypeAdapter(CatalogSpecification).validate_python(load("catalog_specs.yaml"))
    TypeAdapter(dict[DrsType, DrsSpecification]).validate_python(load("drs_specs.yaml"))


def test_attr_specs_value_type_agrees_with_dtype_and_separator(attrs, attr_specs):
    """
    value_type is derived from global_attributes.json, never maintained separately:
      boolean       <- dtype boolean
      string_array  <- separator "space" AND a CV (esgvoc ncattvalid splits on single
                       spaces and validates each piece against the CV; it only does this
                       for the exact value "string_array")
      string        <- everything else
    """
    bad = []
    for e in attr_specs:
        name = _yaml_name(e)
        if name not in attrs:
            continue
        a = attrs[name]
        if a["dtype"] == "boolean":
            want = "boolean"
        elif a["separator"] == "space" and a["cv"] is not None:
            want = "string_array"
        else:
            want = "string"
        if e["value_type"] != want:
            bad.append(
                f"{name}: attr_specs.yaml value_type={e['value_type']!r}, JSON implies {want!r}"
            )
    assert not bad, bad


def test_catalog_regex_id_matches_dataset_id_drs(repo_root, drs_specs):
    """
    catalog_specs.yaml `regex_id` / `regex_title` must describe exactly the dataset id that
    drs_specs.yaml defines: <activity_id>.<middle parts...>.<version>, joined by the DRS
    separator, where the activity is the project's drs_name (obs4MIPs).
    """
    catalog = yaml.safe_load((repo_root / "catalog_specs.yaml").read_text())["catalog_properties"]
    project = yaml.safe_load((repo_root / "project_specs.yaml").read_text())
    ds = drs_specs["dataset_id"]
    parts = [p["source_collection"] for p in ds["parts"]]
    assert parts[0] == "activity_id" and parts[-1] == "version", (
        f"dataset_id must start with activity_id and end with version, got {parts}"
    )
    assert ds["separator"] == ".", f"regex_id assumes '.' separators, got {ds['separator']!r}"

    def make_id(n_middle, version="v20260101"):
        return ds["separator"].join([project["drs_name"], *["Abc-1"] * n_middle, version])

    n_middle = len(parts) - 2
    rid, rtitle = re.compile(catalog["regex_id"]), re.compile(catalog["regex_title"])
    assert rid.match(make_id(n_middle)), (
        f"regex_id does not match a dataset id with {len(parts)} DRS parts ({parts}); "
        f"regex_id={catalog['regex_id']!r}"
    )
    assert not rid.match(make_id(n_middle + 1)) and not rid.match(make_id(n_middle - 1)), (
        "regex_id also accepts ids with a different number of parts"
    )
    # regex_title is the same pattern without the version.
    assert catalog["regex_id"] == catalog["regex_title"][:-1] + r"\.v[0-9]{8}$"
    assert rtitle.match(ds["separator"].join([project["drs_name"], *["Abc-1"] * n_middle]))


def test_catalog_specs_source_collections_are_cv_directories(repo_root):
    """
    esgvoc raises "collection '<x>' is not found" when generating the catalog schema for a
    `source_collection` that is not a project collection (a CV directory). Properties that
    are not backed by a collection must use `source_collection: null` plus a
    `catalog_field_name`.
    """
    catalog = yaml.safe_load((repo_root / "catalog_specs.yaml").read_text())
    dirs = _cv_dirs(repo_root)
    bad = sorted({
        p["source_collection"]
        for key in ("dataset_properties", "file_properties")
        for p in catalog[key]
        if p["source_collection"] is not None and p["source_collection"] not in dirs
    })
    assert not bad, f"catalog_specs.yaml source_collection is not a CV directory: {bad}"


# Required CV-backed global attributes that the STAC catalog deliberately leaves out or keeps
# optional (see "Notes for reviewer" in the README). Anything else must stay in the catalog.
CATALOG_LEAVES_OUT = {"contact", "creation_date", "dataset_contributor", "references"}
CATALOG_KEEPS_OPTIONAL = {"Conventions", "has_aux_unc"}


def test_required_cv_attributes_are_required_cv_properties_in_catalog(attrs, repo_root):
    """
    A required global attribute validated against a CV (`cv` in this file) must be a
    required catalog property sourced from the same CV table (and the same key when the
    key is `description`): otherwise the STAC schema accepts items that the files would
    never be allowed to describe (free text instead of the CV, or the property missing).
    """
    catalog = yaml.safe_load((repo_root / "catalog_specs.yaml").read_text())
    props = [p for s in ("dataset_properties", "file_properties") for p in catalog.get(s) or []]
    bad = []
    for name, a in sorted(attrs.items()):
        if a["requirement"] != "required" or not a.get("cv") or name in CATALOG_LEAVES_OUT:
            continue
        by_description = a["cv"].get("key") == "description"
        matches = [
            p for p in props
            if p["source_collection"] == a["cv"]["table"]
            and (p.get("source_collection_key") == "description") == by_description
        ]
        if not matches:
            bad.append(f"{name}: no catalog property sourced from CV '{a['cv']['table']}'")
        elif name not in CATALOG_KEEPS_OPTIONAL and not all(p["is_required"] for p in matches):
            bad.append(f"{name}: required attribute but optional catalog property")
    assert not bad, bad
