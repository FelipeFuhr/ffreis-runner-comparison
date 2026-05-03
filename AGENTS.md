# Agent Context

**This repo:** `ffreis-runner-comparison` (also known as `ffreis-onnx-runner-comparison`)
— harness that benchmarks and compares Python ONNX serving vs. Rust ONNX serving in
container and native modes.

## Non-obvious facts

- **Scenario-driven architecture.** Each comparison is defined as a `scenario.yaml`
  under `scenarios/<id>/`. Adding a new comparison means adding a scenario directory,
  not changing the harness core.

- **Model artifacts are shared at `/tmp/onnx-runner-comparison/model.onnx`** so both
  Python and Rust implementations test identical ONNX output. Do not let each
  implementation source a different model file.

- **`perf_runner` has two modes:** `deterministic_http` (recommended, uses fixed-size
  request batches) and `request_count` (legacy). Prefer `deterministic_http` for new
  scenarios.

- **`parity_services`** in scenario config controls which implementations must match
  numerically. E.g., Python and Python-sklearn must match; Rust may differ in edge
  cases. Do not remove the parity subset concept.

- **Native mode requires local `uv` + Rust/Cargo.** Container mode uses docker-compose.
  CI only runs container mode.

## Structure

```
scenarios/<id>/
  scenario.yaml           ← metadata, model prep, payload, thresholds, parity_services
config/modes/*.yaml       ← service start commands for native/container
benchmarks/               ← parity and performance test logic
artifacts/                ← generated reports (JSON)
```

## Build/run

```bash
make install
make compare-container               # CI mode
make compare-native-sepal            # native mode with sepal-sum scenario
make report MODE=native SCENARIO=sepal-sum REPORT=artifacts/sepal-report.json
```

## Keeping this file current

- **If you discover a fact not reflected here:** add it before finishing your task.
- **If something here is wrong or outdated:** correct it in the same commit as the code change.
- **If you rename a file, command, or concept referenced here:** update the reference.
