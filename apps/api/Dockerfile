# Stages: `api` (also used by beat), `tex` (adds TeX Live for compile workers) and `ai` (adds matplotlib/pandas for plots).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home app && chown -R app /app


FROM base AS tex
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    latexmk biber \
    texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
    texlive-science texlive-xetex texlive-luatex texlive-bibtex-extra \
    texlive-publishers texlive-plain-generic texlive-fonts-extra \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER app
CMD ["celery", "-A", "config", "worker", "-Q", "compile,transfer", "-l", "info", "--concurrency", "2"]


FROM base AS ai
USER root
COPY requirements-ai.txt .
RUN pip install --no-cache-dir -r requirements-ai.txt
USER app
CMD ["celery", "-A", "config", "worker", "-Q", "ai,import", "-l", "info", "--concurrency", "4"]


FROM base AS api
USER app
EXPOSE 8000
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
