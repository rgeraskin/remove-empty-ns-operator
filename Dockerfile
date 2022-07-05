FROM python:3.10-alpine
COPY src/requirements.txt /src/
RUN pip install -r /src/requirements.txt
COPY src/remove-empty-ns-operator.py /src/
CMD kopf run -n '*' /src/remove-empty-ns-operator.py
