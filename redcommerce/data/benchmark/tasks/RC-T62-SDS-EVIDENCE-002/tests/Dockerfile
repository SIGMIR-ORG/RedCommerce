FROM python:3.12-slim

RUN useradd --create-home --uid 10002 verifier
WORKDIR /verifier
COPY tasks/RC-T62-SDS-EVIDENCE-002/tests/verify.py /verifier/verify.py
COPY tasks/RC-T62-SDS-EVIDENCE-002/tests/private_ground_truth.json /verifier/private_ground_truth.json
COPY tasks/RC-T62-SDS-EVIDENCE-002/research/mandate_commitment.json /verifier/mandate_commitment.json
COPY redcommerce_v3/verifier_commitment_analysis.py /verifier/verifier_commitment_analysis.py
RUN chmod -R 0555 /verifier
USER 10002:10002
ENTRYPOINT ["python", "/verifier/verify.py"]
