FROM python:3.11-slim

# Dépendances système :
#  - libfreetype6/libjpeg/libpng : rendu PDF (reportlab / PyMuPDF)
#  - tesseract-ocr + packs fra/eng : OCR des CV scannés (extract_text_pdf -> _ocr_pdf)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6-dev \
        libjpeg-dev \
        libpng-dev \
        tesseract-ocr \
        tesseract-ocr-fra \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# .env est fourni via env_file dans docker-compose ; le volume ./data:/app/data conserve sessions.db
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
