# Academy Test Setup

Note: This is currently just running the Academy test from the docs.

Tests using remote agents on Aurora, placed by Globus Compute, and
using the online HttpExchange.

## Aurora (Remote)

### First Time Setup

```bash
python -m venv academy-agent --system-site-packages
source academy-agent/bin/activate
pip install academy-py globus-compute-endpoint globus-compute-sdk
globus-compute-endpoint configure aurora
```

Place remote/user_config_template.yaml.j2 in user configuration space.

```bash
${HOME}/.globus_compute/aurora/user_config_template.yaml.j2
```

### Each Time
```bash
source academy-agent/bin/activate
globus-compute-endpoint start aurora
```

The endpoint UUID prints when it starts. Copy it for the laptop setup.
You may need to authenticate on Globas (via a link if given).

To run in background:
```bash
nohup globus-compute-endpoint start aurora &
globus-compute-endpoint list
```

## Laptop (Local)

Python version must match the one on Aurora (for serialization).

### First Time Setup
```bash
conda create -n academy_test python=3.10.14
conda activate academy_test
pip install academy-py globus-compute-sdk
```

### Each Time
```bash
conda activate academy_test
export ACADEMY_ENDPOINT="<endpoint-uuid-from-aurora>"
python run_test.py.py
```

## Troubleshooting

To run test locally without Globus:
```bash
unset ACADEMY_ENDPOINT
python run_test.py.py
```
