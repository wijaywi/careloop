FROM python:3.11.9-slim
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY . /app
RUN useradd --create-home --uid 10001 careloop
USER careloop
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["python", "-m", "api", "--host", "0.0.0.0", "--port", "8000"]
