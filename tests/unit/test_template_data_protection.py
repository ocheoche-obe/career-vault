"""The data-protection guards in template.yaml (ADR-030 amendment 1).

Nothing at runtime exercises DeletionPolicy, UpdateReplacePolicy or the deletion-protection flags:
a regression would pass every other test and surface only in a change set, or in a `sam delete`
that takes the only copy of the data with it. These tests pin the guards on the resources that
hold or key the user's data, and pin that they are unconditional, not gated on IsProd again.
"""

from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "infrastructure" / "template.yaml"


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that keeps CloudFormation short-form tags (!Ref, !If, ...) as tagged values."""


def _tagged(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {f"!{tag_suffix}": value}


_CfnLoader.add_multi_constructor("!", _tagged)


@pytest.fixture(scope="module")
def resources():
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CfnLoader)["Resources"]


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
