FROM python:3.11-slim

WORKDIR /app

COPY requirements_v3.txt .
RUN pip install --no-cache-dir -r requirements_v3.txt

COPY . .

ENV DB_BACKEND=sqlite
ENV SQLITE_PATH=data/tracex.db

EXPOSE 8000

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
