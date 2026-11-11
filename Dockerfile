FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl docker.io && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==2.3.1

WORKDIR /app

# Copy the sources first so the virtualenv is not overwritten afterwards
COPY . .

# Install openhands dependencies into a project-local virtualenv
RUN cd openhands && poetry config virtualenvs.in-project true --local \
    && poetry install --no-root --no-interaction 2>&1 | tail -3
ENV PATH="/app/openhands/.venv/bin:$PATH"

# Install additional dependencies
RUN pip install --no-cache-dir datasets nltk rouge-score fuzzywuzzy python-Levenshtein 2>&1 | tail -3

# Set PYTHONPATH so imports work
ENV PYTHONPATH="/app/openhands:/app"

CMD ["bash"]
