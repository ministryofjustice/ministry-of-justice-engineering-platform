.PHONY: schema-checks test check

# Validate reusable workflow_call schemas used by downstream repositories.
schema-checks:
	bash scripts/validate_reusable_workflow_schemas.sh

# Run unit tests for workflow support scripts.
test:
	python3 -m unittest discover -s tests -p "test_*.py" -v

# One-command local verification before opening a PR.
check: schema-checks test
