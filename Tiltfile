load('ext://restart_process', 'docker_build_with_restart')

app_name = "remove-empty-ns-operator"
image = "rgeraskin/" + app_name

docker_build_with_restart(image,
             ".",
             only=["./src"],
             live_update=[
                 sync(
                     "./src/",
                     "/src/",
                 ),
                 run("cd /src && pip install -r requirements.txt",
                     trigger="src/requirements.txt"),
             ],
             entrypoint="kopf run -n '*' /src/remove-empty-ns-operator.py")

k8s_yaml(kustomize('.'))
