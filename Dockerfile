FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY backend/ backend/
COPY frontend/ frontend/

RUN mkdir -p uploads

ENV PORT=7860
EXPOSE 7860

CMD ["python", "main.py"]
