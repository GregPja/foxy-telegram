FROM python:3.10.0rc1-slim-buster

COPY main.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

CMD ["python3","main.py"]
