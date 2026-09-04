# prototype_api -- Path B (durable) hosting, e.g. Render/Fly/Railway's Docker web-service option.
# See README.md's "Deploying for a real gym session" section for the full runbook, including why
# Path A (a cloudflared tunnel) is recommended for the FIRST session instead.
#
# BUILD CONTEXT MUST BE THE kinetiq-v2/ REPO ROOT, not this directory -- the detector/harness
# imports (gate_config.py, exercise_lib.py, detector/) resolve relative paths up to backend/ and
# exercises/ (see config.py's EXERCISE_LIBRARY_DIR, gate_config.py's _BACKEND_DIR), so the image
# needs evals/gate0/, backend/app/core/, and exercises/ at the SAME relative layout they have in
# the repo, not flattened. Build from the repo root:
#
#   cd kinetiq-v2
#   docker build -f evals/gate0/prototype_api/Dockerfile -t kinetiq-prototype-api .
#   docker run -p 8000:8000 -e PROTOTYPE_API_CORS_ORIGINS="https://your-pwa.example.com" kinetiq-prototype-api
#
# No pose runtime here (no mediapipe/tensorflow/rtmlib) -- this service only runs the geometry
# detector over already-extracted keypoints (README.md's "Architecture reminder"). Confirmed by
# scanning every import in evals/gate0/detector, golden_loader.py, exercise_lib.py, gate_config.py,
# scorers/, labeling/, and backend/app/core/config.py: stdlib only, plus fastapi/uvicorn/pydantic.

FROM python:3.13-slim

WORKDIR /app

# Same pinned versions as requirements.txt (local dev/test uses this exact file -- installing
# unpinned "latest" here instead would let the image drift to different, untested versions).
# httpx is only there for fastapi.testclient (tests); harmless, small, pure-Python -- not worth
# splitting into a second requirements file just to exclude it from the image.
COPY evals/gate0/prototype_api/requirements.txt /app/prototype_api_requirements.txt
RUN pip install --no-cache-dir -r /app/prototype_api_requirements.txt

# Preserve the repo's relative layout: evals/gate0/ imports reach backend/app/core/config.py and
# exercises/*.json via parents[N] path arithmetic, not an installed package -- see the note above.
COPY evals/gate0/ /app/evals/gate0/
COPY backend/app/core/ /app/backend/app/core/
COPY exercises/ /app/exercises/

WORKDIR /app/evals/gate0

# Cloud hosts (Render/Fly/Railway) typically inject $PORT; default to 8000 for a plain `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn prototype_api.main:app --host 0.0.0.0 --port ${PORT}"]
