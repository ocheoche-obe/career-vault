"""Observability helpers for CareerVault Lambdas.

Pre-configured ``aws_lambda_powertools`` primitives (Logger, Tracer, Metrics) plus a
``bind_request_context`` helper that threads the correlation fields from the architecture
doc's log field schema (Section 4.1.1) onto the logger for the lifetime of an invocation.

Every Lambda imports the *same* instances from here so that:
- ``service`` is sourced uniformly from ``POWERTOOLS_SERVICE_NAME``
- ``Metrics`` shares the ``CareerVault`` namespace and the ``Environment`` dimension
- log lines carry ``correlation_id`` / ``user_id`` without each handler re-implementing it

Usage in a handler::

    from careervault.observability import logger, tracer, metrics, bind_request_context

    @logger.inject_lambda_context
    @tracer.capture_lambda_handler
    @metrics.log_metrics
    def handler(event, context):
        bind_request_context(event)
        ...
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from aws_lambda_powertools import Logger, Metrics, Tracer

# `service` is read from POWERTOOLS_SERVICE_NAME (set per-Lambda in the SAM template).
logger = Logger()
tracer = Tracer()

# Namespace + the Environment dimension are applied to every custom metric. The namespace
# also honours POWERTOOLS_METRICS_NAMESPACE when set (it is, in Globals.Function).
metrics = Metrics(namespace=os.environ.get("POWERTOOLS_METRICS_NAMESPACE", "CareerVault"))
metrics.set_default_dimensions(Environment=os.environ.get("ENVIRONMENT", "dev"))


def _claims(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the Cognito JWT claims from a REST API Gateway proxy event.

    REST API (``AWS::Serverless::Api``) with a Cognito User Pools authorizer exposes claims
    at ``requestContext.authorizer.claims``. (HTTP API / v2 nests them under ``.jwt.claims`` —
    not what CareerVault uses; see ADR-025 and architecture Section 4.2.4.)
    """
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    ) or {}


def bind_request_context(event: Mapping[str, Any]) -> None:
    """Append correlation fields to the logger for the rest of this invocation.

    Threads ``correlation_id`` (the API Gateway request id) and ``user_id`` (the Cognito
    ``sub`` claim) onto every subsequent log line, per the field schema in Section 4.1.1.
    Safe to call even when fields are absent (e.g. local/unit invocations).
    """
    request_context = event.get("requestContext", {}) or {}
    correlation_id = request_context.get("requestId")
    user_id = _claims(event).get("sub")

    extra: dict[str, str] = {}
    if correlation_id:
        extra["correlation_id"] = correlation_id
    if user_id:
        extra["user_id"] = user_id
    if extra:
        logger.append_keys(**extra)
