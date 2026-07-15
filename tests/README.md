# Tests

Tests are separated into unit, contract, API, architecture, integration, and security
regression suites.
The editing suite covers the RFC 6902 subset and pointer edge cases; repository
tests cover compare-and-swap, concurrent writers, undo/redo, audit atomicity, and
defensive copies. Integration tests use the real JSON Schema and Shapely pipeline
to prove invalid patches cannot create revisions.

`security_tests/` exercises strict JSON admission, non-finite and oversized geometry,
request-body and Patch budgets, Agent authorization, forged audit metadata,
tenant/domain HMAC isolation, and concurrent revision initialization.
