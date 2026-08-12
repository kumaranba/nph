"""Tests for patient tags: model normalization, add/remove mutations (RBAC),
tag suggestions (typeahead), and searching patients by tag (ANY/ALL)."""
import pytest

from api.models import Patient, Tag, TagCategory

# --- GraphQL documents ------------------------------------------------------

ADD_TAGS = """
mutation Add($patientId: ID!, $tags: [String!]!, $category: TagCategoryEnum) {
  addPatientTags(patientId: $patientId, tags: $tags, category: $category) {
    id
    tags { name label category }
  }
}
"""

REMOVE_TAG = """
mutation Remove($patientId: ID!, $tag: String!) {
  removePatientTag(patientId: $patientId, tag: $tag) {
    id
    tags { label }
  }
}
"""

TAG_SUGGESTIONS = """
query Suggest($query: String, $category: TagCategoryEnum) {
  tagSuggestions(query: $query, category: $category) {
    label
    category
    patientCount
  }
}
"""

PATIENTS_BY_TAGS = """
query ByTags($tags: [String!]!, $match: TagMatchEnum) {
  patientsByTags(tags: $tags, match: $match) {
    name
    tags
  }
}
"""


@pytest.fixture
def patient(db):
    return Patient.objects.create(
        name="Jane Doe", age=40, diagnosis="Dx", admitting_doctor="Dr. S"
    )


# --- Model ------------------------------------------------------------------

def test_get_or_create_normalized_dedupes_case_insensitively(db):
    tag1, created1 = Tag.get_or_create_normalized("Aggressive")
    tag2, created2 = Tag.get_or_create_normalized("aggressive")
    assert created1 is True and created2 is False
    assert tag1 == tag2
    # First spelling is preserved as the display label.
    assert tag1.label == "Aggressive"
    assert tag1.name == "aggressive"


def test_get_or_create_normalized_ignores_blank(db):
    tag, created = Tag.get_or_create_normalized("   ")
    assert tag is None and created is False


# --- Add / remove mutations -------------------------------------------------

def test_nurse_can_add_tags_creating_new_ones(nurse_client, patient):
    result = nurse_client.execute(
        ADD_TAGS,
        {"patientId": str(patient.id), "tags": ["Aggressive", "Schizophrenia"],
         "category": "BEHAVIOUR"},
    )
    assert result.get("errors") is None
    labels = {t["label"] for t in result["data"]["addPatientTags"]["tags"]}
    assert labels == {"Aggressive", "Schizophrenia"}
    # Category applies to newly created tags.
    assert Tag.objects.get(name="aggressive").category == TagCategory.BEHAVIOUR


def test_adding_existing_tag_is_idempotent(nurse_client, patient):
    nurse_client.execute(ADD_TAGS, {"patientId": str(patient.id), "tags": ["Calm"]})
    nurse_client.execute(ADD_TAGS, {"patientId": str(patient.id), "tags": ["calm"]})
    assert patient.tags.count() == 1
    assert Tag.objects.filter(name="calm").count() == 1


def test_finance_cannot_add_tags(finance_client, patient):
    result = finance_client.execute(
        ADD_TAGS, {"patientId": str(patient.id), "tags": ["X"]}
    )
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_remove_tag_detaches_but_keeps_tag_row(nurse_client, patient):
    nurse_client.execute(ADD_TAGS, {"patientId": str(patient.id), "tags": ["Calm", "Aggressive"]})
    result = nurse_client.execute(
        REMOVE_TAG, {"patientId": str(patient.id), "tag": "calm"}
    )
    assert result.get("errors") is None
    remaining = {t["label"] for t in result["data"]["removePatientTag"]["tags"]}
    assert remaining == {"Aggressive"}
    # Tag row itself is preserved for the shared vocabulary.
    assert Tag.objects.filter(name="calm").exists()


# --- Suggestions ------------------------------------------------------------

def test_tag_suggestions_typeahead_and_ranking(admin_client, db):
    p1 = Patient.objects.create(name="A", age=1, diagnosis="d", admitting_doctor="x")
    p2 = Patient.objects.create(name="B", age=1, diagnosis="d", admitting_doctor="x")
    admin_client.execute(ADD_TAGS, {"patientId": str(p1.id), "tags": ["Aggressive"]})
    admin_client.execute(ADD_TAGS, {"patientId": str(p2.id), "tags": ["Aggressive"]})
    admin_client.execute(ADD_TAGS, {"patientId": str(p1.id), "tags": ["Agitated"]})

    # Substring "ag" matches both, most-used first.
    result = admin_client.execute(TAG_SUGGESTIONS, {"query": "ag"})
    labels = [t["label"] for t in result["data"]["tagSuggestions"]]
    assert labels == ["Aggressive", "Agitated"]
    assert result["data"]["tagSuggestions"][0]["patientCount"] == 2


def test_tag_suggestions_filtered_by_category(admin_client, db):
    p = Patient.objects.create(name="A", age=1, diagnosis="d", admitting_doctor="x")
    admin_client.execute(ADD_TAGS, {"patientId": str(p.id), "tags": ["Aggressive"], "category": "BEHAVIOUR"})
    admin_client.execute(ADD_TAGS, {"patientId": str(p.id), "tags": ["Diabetes"], "category": "ILLNESS"})

    result = admin_client.execute(TAG_SUGGESTIONS, {"category": "ILLNESS"})
    labels = [t["label"] for t in result["data"]["tagSuggestions"]]
    assert labels == ["Diabetes"]


# --- Search by tag ----------------------------------------------------------

def test_patients_by_tags_any_vs_all(admin_client, db):
    p1 = Patient.objects.create(name="Alpha", age=1, diagnosis="d", admitting_doctor="x")
    p2 = Patient.objects.create(name="Beta", age=1, diagnosis="d", admitting_doctor="x")
    admin_client.execute(ADD_TAGS, {"patientId": str(p1.id), "tags": ["Aggressive", "Diabetes"]})
    admin_client.execute(ADD_TAGS, {"patientId": str(p2.id), "tags": ["Aggressive"]})

    # ANY: both patients carry "Aggressive".
    any_res = admin_client.execute(
        PATIENTS_BY_TAGS, {"tags": ["Aggressive"], "match": "ANY"}
    )
    assert {r["name"] for r in any_res["data"]["patientsByTags"]} == {"Alpha", "Beta"}

    # ALL: only Alpha carries both.
    all_res = admin_client.execute(
        PATIENTS_BY_TAGS, {"tags": ["Aggressive", "Diabetes"], "match": "ALL"}
    )
    names = [r["name"] for r in all_res["data"]["patientsByTags"]]
    assert names == ["Alpha"]
    # Result rows carry the patient's tag labels.
    assert set(all_res["data"]["patientsByTags"][0]["tags"]) == {"Aggressive", "Diabetes"}


def test_patients_by_tags_empty_returns_empty(admin_client, db):
    result = admin_client.execute(PATIENTS_BY_TAGS, {"tags": []})
    assert result["data"]["patientsByTags"] == []
