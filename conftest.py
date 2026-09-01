"""Ensures the repository root is on sys.path so `import audit_pipeline`
resolves inside tests/, regardless of pytest's per-file import-mode rules.
"""
