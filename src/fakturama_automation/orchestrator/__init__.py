"""Orchestrator package.

Implements the state machine that drives the whole workflow: extraction,
normalization, order population, order line entry and verification, order
save and verification, invoice creation and verification, and payment
status application and verification. Any ambiguous match or failed
verification stops the flow via error_handling.
"""
