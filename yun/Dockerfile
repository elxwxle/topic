FROM python:3.11-slim

WORKDIR /yun

COPY requirements.txt /yun/requirements.txt
RUN pip install --no-cache-dir -r /yun/requirements.txt

COPY . /yun

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]