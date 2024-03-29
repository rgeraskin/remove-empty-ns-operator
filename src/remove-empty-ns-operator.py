# #!/usr/bin/env python3

import re

import kopf
import yaml
from kubernetes import client, config, dynamic
from kubernetes.dynamic.resource import ResourceList

# config.load_kube_config()
config.load_incluster_config()
core_api = client.CoreV1Api()
dynamic_client = dynamic.DynamicClient(client.api_client.ApiClient())
annotation = "remove-empty-ns-operator.kopf.dev/will-remove"

with open("/config/settings.yaml") as f:
    settings = yaml.safe_load(f)
interval = int(settings["interval"])

initial_delay = int(settings["initialDelay"])
ignored_resouces = settings["ignoredResouces"]
protected_namespaces = settings.get("protectedNamespaces", [])


@kopf.timer('namespaces',
            interval=interval,
            initial_delay=initial_delay,
            when=lambda name, **_: name not in protected_namespaces)
def remove_empty_ns(status, name, body, logger, **kwargs):
    global core_api
    meta = body["metadata"]

    try:
        should_remove = meta["annotations"][annotation] == "True"
    except KeyError:
        should_remove = False

    if is_empty(name, logger):
        if should_remove:
            logger.info(f"namespace {name} has deletion mark, deleting")
            core_api.delete_namespace(name=name)
        else:
            logger.info(f"namespace {name} is empty, "
                        f"adding deletion mark to delete it next time")
            add_will_remove_annotation(name, meta)
    elif should_remove:
        logger.info(
            f"namespace {name} is not empty anymore, removing deletion mark")
        del_will_remove_annotation(name, meta)


def add_will_remove_annotation(name, meta):
    patch_will_remove_annotation(name, meta, "True")


def del_will_remove_annotation(name, meta):
    patch_will_remove_annotation(name, meta, None)


def patch_will_remove_annotation(name, meta, value):
    global annotation, core_api

    meta.setdefault("annotations", {}).update({annotation: value})
    for unexpected_argument in ('resourceVersion', 'creationTimestamp',
                                'managedFields'):
        try:
            del meta[unexpected_argument]
        except KeyError:
            pass
    data = client.V1Namespace(metadata=client.V1ObjectMeta(**meta))
    core_api.patch_namespace(name=name, body=data)


def is_empty(namespace, logger):
    global ignored_resouces, dynamic_client

    for api_resource in dynamic_client.resources:
        if (not isinstance(api_resource[0], ResourceList)
                and "get" in api_resource[0].verbs
                and api_resource[0].namespaced
                and api_resource[0].kind != "Event"):
            api_resource = api_resource[0]

            resource_instance = api_resource.get(namespace=namespace)

            items = resource_instance.items
            for item in items:
                logger.debug(f"{namespace=}: found {api_resource.group=} "
                             f"{api_resource.kind=} name={item.metadata.name}")
                ignored = False
                for ignored_resource in ignored_resouces:
                    if (api_resource.group == ignored_resource["apiGroup"]
                            and api_resource.kind == ignored_resource["kind"]
                            and re.match(ignored_resource["nameRegExp"],
                                         item.metadata.name)):
                        ignored = True
                        logger.debug(
                            f"{namespace=}: name={item.metadata.name} "
                            f"should be ignored")
                        break
                if not ignored:
                    logger.debug(f"{namespace=} is not empty")
                    return False
    return True
