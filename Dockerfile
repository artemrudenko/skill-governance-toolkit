FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY scripts/build_index.py /app/scripts/build_index.py
COPY scripts/agent_audit.py /app/scripts/agent_audit.py
COPY scripts/agent_governance_mcp.py /app/scripts/agent_governance_mcp.py
COPY references/agent-audit-rules.json /app/references/agent-audit-rules.json
# Data files the engine loads at runtime. Without unicode-confusables.json,
# load_confusables() returns empty and SEC003 homoglyph detection silently dies;
# without audit-ignore.json the central suppression list is unavailable. Both
# loaders tolerate absence, so a missing COPY degrades features with no error.
COPY references/unicode-confusables.json /app/references/unicode-confusables.json
COPY references/audit-ignore.json /app/references/audit-ignore.json
# VERSION is read at runtime by agent_audit.engine_version() (parents[1]/VERSION).
# Without it every audit report is stamped engine_version="unknown".
COPY VERSION /app/VERSION

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
  && chown -R appuser:appuser /app /workspace

USER appuser

ENTRYPOINT ["python3", "/app/scripts/agent_governance_mcp.py"]
