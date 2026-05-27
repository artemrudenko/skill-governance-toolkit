FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY scripts/build_index.py /app/scripts/build_index.py
COPY scripts/agent_audit.py /app/scripts/agent_audit.py
COPY scripts/agent_governance_mcp.py /app/scripts/agent_governance_mcp.py
COPY references/agent-audit-rules.json /app/references/agent-audit-rules.json

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
  && chown -R appuser:appuser /app /workspace

USER appuser

ENTRYPOINT ["python3", "/app/scripts/agent_governance_mcp.py"]
