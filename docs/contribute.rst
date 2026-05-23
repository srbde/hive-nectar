Contributing to nectar
======================

We welcome your contributions to our project.

Repository
----------

The repository of nectar is currently located at:

    https://github.com/srbde/hive-nectar

Development Workflow
--------------------

We use modern Python tooling to maintain code quality:

*   **uv**: Package and environment management.
*   **ruff**: Fast Python linting and formatting.
*   **ty**: Type checking.
*   **pytest**: Testing framework.

How to Contribute
-----------------

1. **Fork** the repo on GitHub.
2. **Clone** the project to your own machine.
3. **Install** development dependencies: `uv sync --dev`.
4. **Create a branch** for your changes.
5. **Implement** your changes and add tests.
6. **Verify** your changes:
    *   Run tests: `uv run pytest`
    *   Check linting: `uv tool run ruff check`
    *   Check types: `uv tool run ty check`
7. **Push** your work to your fork.
8. Submit a **Pull request** to the `main` branch.

Issues
------

Feel free to submit issues and enhancement requests on our `GitHub Issues <https://github.com/srbde/hive-nectar/issues>`_ page.

Copyright and Licensing
-----------------------

This library is open source under the MIT license. We require you to
release your code under that license as well.
