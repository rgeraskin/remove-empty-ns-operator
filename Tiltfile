load("ext://restart_process", "docker_build_with_restart")
load("ext://helm_resource", "helm_resource", "helm_repo")

app_name = "remove-empty-ns-operator"
image = app_name

docker_build_with_restart(
    image,
    ".",
    only=[
        "./src",
        "pyproject.toml",
        "poetry.lock",
    ],
    live_update=[
        sync(
            "./src/",
            "/app/",
        ),
    ],
    entrypoint="kopf run -n '*' /app/app.py"
)

helm_resource(
    app_name,
    "./helm",
    namespace=app_name,
    flags=[
        "--create-namespace",
        "--set=settings.interval=5",
        "--set=settings.initialDelay=5",
        "--set=settings.protectedNamespaces[0]=protected-one",
    ],
    deps=[".helm"],
    image_deps=[image],
    image_keys=[("image.repository", "image.tag")],
)
