.PHONY: clean-pyc clean-build docs generate-versions

clean: clean-build clean-pyc

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info
	rm -fr __pycache__/ .eggs/ .cache/ .tox/

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

generate-versions:
	python3 generate_versions.py

lint:
	uv run ruff check src

format:
	uv run ruff format src

imports:
	uv run ruff check --select I --fix src

test:
	python3 -m pytest -v

build: generate-versions
	uv build

install: build
	uv pip install -e .

git:
	git push --all
	git push --tags

check:
	uv pip check

dev-setup:
	uv sync --dev

dist: generate-versions
	uv build
	uvx uv-publish@latest --repo pypi

tag:
	@VERSION=$$(grep -m1 '^version[[:space:]]*=' pyproject.toml | cut -d '"' -f2) && \
	echo "Creating git tag v$$VERSION" && \
	git tag -a "v$$VERSION" -m "Release v$$VERSION"

test-dist: generate-versions
	uv build
	uvx uv-publish@latest --repo testpypi

docs:
	uv run sphinx-apidoc -H "API Reference" -d 4 -e -f -o docs src
	rm -rf docs/_build/html docs/_build/doctrees
	uv run sphinx-build -b html docs docs/_build/html

release: clean check dist tag git
