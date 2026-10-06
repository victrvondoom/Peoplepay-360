FROM python:3.12-slim
WORKDIR /peoplepay
COPY extensions/civicmesh/requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=peoplepay_build_ca,required=false \
    if [ -s /run/secrets/peoplepay_build_ca ]; then \
      PIP_CERT=/run/secrets/peoplepay_build_ca pip install --no-cache-dir -r /tmp/requirements.txt; \
    else pip install --no-cache-dir -r /tmp/requirements.txt; fi
COPY CivicMesh-main /peoplepay/CivicMesh-main
COPY extensions/__init__.py /peoplepay/extensions/__init__.py
COPY extensions/civicmesh /peoplepay/extensions/civicmesh
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1
EXPOSE 8092
CMD ["python", "-m", "uvicorn", "extensions.civicmesh.service:app", "--host", "0.0.0.0", "--port", "8092"]
