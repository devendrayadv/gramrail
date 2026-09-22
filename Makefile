.PHONY: test check build

test:
	python -m pytest
	 node --test sdk/javascript/test.mjs
	cd sdk/go && go test -race ./... && go vet ./...

check:
	python scripts/check.py

build:
	python -m build
