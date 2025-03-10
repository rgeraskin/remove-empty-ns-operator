FROM python:3.12-alpine
COPY src/requirements.txt /src/
RUN pip install -r /src/requirements.txt
COPY src/remove_empty_ns_operator.py /src/
CMD kopf run -n '*' /src/remove_empty_ns_operator.py
