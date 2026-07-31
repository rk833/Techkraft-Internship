# Build from the repository root, not this folder, because the image needs
# common/ and requirements.txt as well:
#
#     docker build -f 15-Production-AI/Dockerfile -t ai-chat-api .

FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: no .pyc files, they are useless in an image
# PYTHONUNBUFFERED: logs appear immediately rather than being held in a buffer,
#   which otherwise makes a crashed container look like it said nothing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements-api.txt, not the repository's requirements.txt. The API imports
# a small fraction of what the fifteen modules need, and shipping the rest would
# add hundreds of megabytes for nothing.
#
# Dependencies are copied and installed before the source, so editing code does
# not invalidate the cached install layer. This is the single biggest thing you
# can do for rebuild speed.
COPY 15-Production-AI/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY common/ ./common/
COPY 15-Production-AI/app.py .

# Run as a non-root user. A container process that does not need root should
# not have it, so that a flaw in the application is not also a flaw in the host.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# No secrets are baked in. GOOGLE_API_KEY and SERVICE_API_KEYS are passed at
# run time, because anything in the image is readable by anyone who can pull it:
#
#     docker run -p 8000:8000 -e GOOGLE_API_KEY=... -e SERVICE_API_KEYS=... ai-chat-api
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
