FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=itsanet_build_ca \
    if [ -r /run/secrets/itsanet_build_ca ]; then export PIP_CERT=/run/secrets/itsanet_build_ca; fi; \
    pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --gid 10001 itsanet \
    && useradd --uid 10001 --gid 10001 --no-create-home itsanet \
    && mkdir -p /var/lib/itsanet /opt/itsanet \
    && chown itsanet:itsanet /var/lib/itsanet
WORKDIR /opt/itsanet
USER 10001:10001
