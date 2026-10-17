FROM python:3.12-slim

RUN useradd --create-home --uid 10001 agent
WORKDIR /workspace
COPY tasks/RC-T22-SEARCH-AD-001/environment/driver.py /opt/redcommerce/driver.py
RUN chmod -R 0555 /opt/redcommerce && chown agent:agent /workspace
USER 10001:10001
CMD ["sh", "-lc", "sleep infinity"]
