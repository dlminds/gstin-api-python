# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-09-08

First release.

### Added

- **Offline GSTIN validation** with no dependencies: format check, modulus-36
  check digit, and a rejection reason written for the person who typed the
  number.
- **Structural parsing** — state, embedded PAN, PAN holder type, entity code,
  registration number within the state, expected vs actual check digit — plus a
  labelled five-part breakdown for UI.
- **`buildGstin` / `build_gstin`** for generating checksum-correct numbers in
  test fixtures.
- **The GST state-code table**, including which codes levy UTGST rather than
  SGST and which are no longer issued.
- **API client** for the gstinapi.com GST verification API: single lookups, a
  non-throwing `verify`, and a bulk `verifyMany` / `verify_many` that
  deduplicates, skips malformed rows without spending a credit, and aborts
  cleanly when the account runs out of credits.
- **Automatic retries** with exponential backoff and full jitter for 429, 5xx and
  transport failures, honouring `Retry-After`. 401 and 402 are never retried.
- **A `gstin-api` command line** covering validate, parse, explain, states and
  lookup, reading from stdin so it composes with `cut`, `grep` and friends.
- **A parity test suite** pinned to the shared corpus that the gstinapi.com PHP
  implementation and the Google Sheets add-on also assert against.

[Unreleased]: https://github.com/dlminds/gstin-api-python/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dlminds/gstin-api-python/releases/tag/v0.1.0
