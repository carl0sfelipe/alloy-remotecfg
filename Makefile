PYTHON := ./venv/bin/python
PIP := ./venv/bin/pip

.PHONY: install serve smoke portal reset test

install:
	python3 -m venv venv
	$(PIP) install -r requirements.txt
	$(PYTHON) -m grpc_tools.protoc -I proto --python_out=gen --grpc_python_out=gen proto/collector.proto
	touch gen/__init__.py
	$(PYTHON) reset.py

serve:
	$(PYTHON) server.py --port 9090

smoke:
	$(PYTHON) smoke.py --addr 127.0.0.1:9090

portal:
	$(PYTHON) portal.py --port 8080

reset:
	$(PYTHON) reset.py

test:
	$(PYTHON) -m grpc_tools.protoc -I proto --python_out=gen --grpc_python_out=gen proto/collector.proto
	touch gen/__init__.py
	$(PYTHON) -m unittest discover -s tests -v
