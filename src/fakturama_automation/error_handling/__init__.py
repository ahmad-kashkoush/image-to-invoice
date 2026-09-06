"""Error handling package.

The single stop point reached from any ambiguous match or failed
verification anywhere in the workflow. Nothing should retry indefinitely
or silently continue past a failure; it should land here for manual review.
"""
