FROM python:3.11-slim
WORKDIR /app
COPY simulatie/requirements.txt simulatie/requirements.txt
RUN pip install --no-cache-dir -r simulatie/requirements.txt
COPY . .
EXPOSE 8000
# scenario's en runs staan in simulatie/scenarios en simulatie/runs: koppel die als volume om ze te bewaren
CMD ["uvicorn", "webapp.main:app", "--app-dir", "simulatie", "--host", "0.0.0.0", "--port", "8000"]
