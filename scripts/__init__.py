"""Repository maintenance and publication tooling.

The package marker keeps imports deterministic when the test suite runs from
the Docker publication workspace, where an unrelated third-party ``scripts``
namespace may otherwise take precedence.
"""
