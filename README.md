# CPPS Circular Factory Usecases JMS

This repository packages two runnable use-case slices around the FlexConveyor and GraphDB stack:

- A Streamlit-based FlexConveyor visualizer and runtime bootstrapper
- A vertical integration demo with a mock time-series backend

The primary supported installation flow is Poetry.

## Requirements

- Python 3.12 or 3.13
- Poetry
- A reachable GraphDB instance

GraphDB is an external prerequisite. It is not bundled by this repository.

## Installation

```bash
git clone https://github.com/EHoffm/CPPS_Circular_factory_usecases_JMS.git
cd CPPS_Circular_factory_usecases_JMS
poetry install --with dev
```

The `--with dev` variant is recommended because it also installs the smoke-test and linting toolchain.

## Run The Visualizer

```bash
poetry run flexconveyor-interface
```

This starts the Streamlit visualizer. The UI lets you connect to GraphDB manually by entering:

- Base URL
- Repository name
- Username
- Password

If you already use environment-based GraphDB credentials, the visualizer also exposes a login path based on `GraphDBCredentials.from_env()`.

## Run The Vertical Integration Demo

```bash
poetry run vertical-integration-demo
```

The demo starts a local mock time-series service on `http://127.0.0.1:5050` and then interacts with GraphDB through `GraphDB.from_env()`. For that flow, provide the GraphDB environment variables expected by `graph_db_interface` before starting the demo.

## Validate The Install

```bash
poetry run pytest tests/test_install_smoke.py -q
```

This smoke test verifies two things:

- packaged CSV resources for the vertical integration demo are available
- the supported module surface imports cleanly after installation

## Repository Layout

```text
CPPS_Circular_factory_usecases_JMS/
├── Usecase_FlexConveyor_decentral/
│   └── src/
│       ├── FlexConveyor_Module/
│       ├── Mock_WMS/
│       └── Visualizer/
├── Usecase_Vertical_integration/
│   ├── demo.py
│   ├── db.py
│   └── unscrewing_timeseries/
├── tests/
├── pyproject.toml
└── README.md
```

## Development

Useful commands during development:

```bash
poetry run pytest
poetry run pytest tests/test_install_smoke.py -q
poetry build
pre-commit install
```
