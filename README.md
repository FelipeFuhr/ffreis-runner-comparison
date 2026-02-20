# ONNX Runner Comparison Harness

Compares Python and Rust ONNX serving implementations in two modes:

- `container`: starts both services with Docker/Podman Compose
- `native`: starts both services as local processes

## Quick start

```bash
cd ffreis-onnx-runner-comparison
make install
make compare-container
make compare-native
make compare-native-sepal
make compare-native-triple
make compare-native-raw-all
make report MODE=native SCENARIO=sepal-sum REPORT=artifacts/sepal-report.json
```

## What runs

- parity smoke checks (HTTP)
- property-based checks (Hypothesis)
- per-scenario latency comparison (mean/p95/rps)
- JSON report output in `artifacts/` (default: `artifacts/comparison-report.json`)

## Scenario folders

Scenarios live in `scenarios/<scenario-id>/` and each folder contains:

- `scenario.yaml`: scenario metadata + model preparation + request + thresholds
- `payload.csv` (or other payload file): request body used for parity and perf runs
- `testset.csv`: optional dataset reference for scenario documentation/extension
- `model/model.onnx` (optional): prebuilt model artifact for model-copy workflow

Current runnable scenario:

- `scenarios/sepal-sum/`

Template for AutoSklearn:

- `scenarios/autosklearn-sepal-template/` (`enabled: false` until model is added)
- `scenarios/raw-all-frameworks/` (python raw backends + rust ONNX)

To run selected scenarios:

```bash
cd ffreis-onnx-runner-comparison
make compare MODE=native SCENARIO=sepal-sum
make compare MODE=native SCENARIO=sepal-sum,another-scenario
make compare MODE=native SCENARIO=all
```

Useful `compare` fields in `scenario.yaml`:

- `baseline_service`: service id used for perf ratio comparisons.
- `parity_services`: optional subset of services to enforce exact parity.
  - Example: compare parity for `python` and `python_sklearn`, while still
    benchmarking `rust`.
- `perf_runner`: `deterministic_http` (recommended) or `request_count` (legacy).
- `warmup_requests`, `max_mean_ratio`, `max_p95_ratio`.
- For `deterministic_http`: `rate_rps`, `duration_s`.
- For `request_count`: `measured_requests`.

In native mode, this scenario starts three services for comparison:

- `python` (ONNX)
- `python_sklearn` (native sklearn model)
- `rust` (ONNX)

## Notes

- This scaffold is intentionally minimal and safe to evolve.
- Update commands/endpoints in `config/modes/*.yaml` for your machine.
- `native` mode expects `uv` and Rust/Cargo installed locally.
- Scenario model setup currently targets `/tmp/onnx-runner-comparison/model.onnx`
  so both implementations use the exact same ONNX file.
