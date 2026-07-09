.DEFAULT_GOAL := help

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

test:  ## Run the offline test suite (recorded fixtures, no credentials)
	python3 -m pytest -q

lint:  ## Run ruff
	python3 -m ruff check src tests

dry-run:  ## Fetch yesterday's digest and print the embed without posting (needs GA env vars)
	python3 -m ga_discord_bridge --dry-run

.PHONY: help test lint dry-run
