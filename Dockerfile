ARG PYTHON_VERSION=3.12-alpine
# Stage 1: Build
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /app

# Copy only the necessary files for installing dependencies
COPY pyproject.toml poetry.lock ./

# Install Poetry and dependencies
RUN pip install poetry poetry-plugin-export
RUN poetry export -o requirements.txt

# Stage 2: Final
FROM python:${PYTHON_VERSION} AS production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy the requirements.txt file from the builder stage to the current directory
COPY --from=builder /app/requirements.txt .

# Set the UID argument to a default value of 10001
ARG UID=10001

# Create a new user with the specified UID and set its properties
# Install the Python packages listed in the requirements.txt file
RUN --mount=type=cache,target=/root/.cache/pip \
    adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser \
 && chown -R appuser /app \
 && python -m pip install -r requirements.txt

 # Copy the rest of the project files
COPY src/app.py app.py

# Set the user to run the container as
USER appuser

# Set the entry point for your application
ENTRYPOINT ["kopf", "run", "-n", "*", "app.py"]
