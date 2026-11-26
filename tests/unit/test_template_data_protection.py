"""The data-protection guards in template.yaml (ADR-030 amendment 1).

Nothing at runtime exercises DeletionPolicy, UpdateReplacePolicy or the deletion-protection flags:
a regression would pass every other test and surface only in a change set, or in a `sam delete`
that takes the only copy of the data with it. These tests pin the guards on the resources that
hold or key the user's data, and pin that they are unconditional, not gated on IsProd again.
"""

import pytest
from helpers import load_template_resources


@pytest.fixture(scope="module")
def resources():
    return load_template_resources()


@pytest.mark.parametrize("logical_id", ["CareerVaultTable", "DataBucket", "CognitoUserPool"])
def test_data_resources_are_retained_in_every_environment(resources, logical_id):
    resource = resources[logical_id]
    # A literal "Retain", not an !If: the dev stack holds the only copy of the data (ADR-041).
    assert resource.get("DeletionPolicy") == "Retain"
    assert resource.get("UpdateReplacePolicy") == "Retain"


def test_table_has_deletion_protection_and_pitr(resources):
    props = resources["CareerVaultTable"]["Properties"]
    assert props["DeletionProtectionEnabled"] is True
    assert props["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"] is True


def test_user_pool_has_deletion_protection(resources):
    # Every item's PK is USER#<sub> and only this pool issues that sub.
    assert resources["CognitoUserPool"]["Properties"]["DeletionProtection"] == "ACTIVE"
