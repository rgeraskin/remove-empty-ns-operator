#!/usr/bin/env python3

"""Kubernetes operator that automatically removes empty namespaces."""

import re

import kopf
import yaml
from kubernetes import client, config, dynamic
from kubernetes.dynamic.resource import ResourceList

ANNOTATION = "remove-empty-ns-operator.kopf.dev/will-remove"
FINALIZER = "kopf.zalando.org/KopfFinalizerMarker"

# config.load_kube_config()
config.load_incluster_config()
core_api = client.CoreV1Api()
dynamic_client = dynamic.DynamicClient(client.api_client.ApiClient())

with open("/config/settings.yaml", encoding="utf-8") as f:
    settings = yaml.safe_load(f)

interval = settings["interval"]
initial_delay = settings["initialDelay"]
ignored_resouces = settings["ignoredResouces"]
protected_namespaces = settings.get("protectedNamespaces", [])


@kopf.on.cleanup()
async def cleanup(logger, **_):
    """Remove finalizers from all namespaces during operator shutdown."""
    logger.info("Shutting down")
    if not settings["cleanupFinalizers"]:
        logger.info("cleanupFinalizers is disabled, skipping")
        return

    # for every namespace, remove the finalizer
    for namespace in core_api.list_namespace().items:
        if namespace.metadata.finalizers and FINALIZER in namespace.metadata.finalizers:
            # remove the finalizer from list
            logger.info(f"Removing finalizer from namespace={namespace.metadata.name}")
            namespace.metadata.finalizers.remove(FINALIZER)
            # https://github.com/kubernetes-client/python/issues/2307#issuecomment-2483720199
            patch = [
                {
                    "op": "replace",
                    "path": "/metadata/finalizers",
                    "value": namespace.metadata.finalizers,
                }
            ]
            core_api.patch_namespace(namespace.metadata.name, patch)
    logger.info("Cleanup finalizers completed")


@kopf.timer(
    "namespaces",
    interval=interval,
    initial_delay=initial_delay,
    when=lambda name, **_: name not in protected_namespaces,
)
# pylint: disable=unused-argument
def remove_empty_ns(status, name, body, logger, **_):
    """Check if namespace is empty and mark it for deletion if needed."""
    meta = body["metadata"]

    try:
        should_remove = meta["annotations"][ANNOTATION] == "True"
    except KeyError:
        should_remove = False

    if is_empty(name, logger):
        if should_remove:
            if settings["dryRun"]:
                logger.info(
                    f"namespace {name} has deletion mark, "
                    f"would be deleted but dry-run is enabled"
                )
            else:
                logger.info(f"namespace {name} has deletion mark, deleting")
                core_api.delete_namespace(name=name)
        else:
            logger.info(
                f"namespace {name} is empty, "
                f"adding deletion mark to delete it next time"
            )
            add_will_remove_annotation(name, meta)
    elif should_remove:
        logger.info(f"namespace {name} is not empty anymore, removing deletion mark")
        del_will_remove_annotation(name, meta)


def add_will_remove_annotation(name, meta):
    """Add annotation to mark namespace for deletion."""
    patch_will_remove_annotation(name, meta, "True")


def del_will_remove_annotation(name, meta):
    """Remove deletion annotation from namespace."""
    patch_will_remove_annotation(name, meta, None)


def patch_will_remove_annotation(name, meta, value):
    """Update namespace with deletion annotation value."""
    meta.setdefault("annotations", {}).update({ANNOTATION: value})
    for unexpected_argument in (
        "resourceVersion",
        "creationTimestamp",
        "managedFields",
    ):
        try:
            del meta[unexpected_argument]
        except KeyError:
            pass
    data = client.V1Namespace(metadata=client.V1ObjectMeta(**meta))
    core_api.patch_namespace(name=name, body=data)


def is_empty(namespace, logger):
    """Check if namespace not contains any non-ignored resources."""
    for api_resource in dynamic_client.resources:
        if (
            not isinstance(api_resource[0], ResourceList)
            and "get" in api_resource[0].verbs
            and api_resource[0].namespaced
            and api_resource[0].kind != "Event"
        ):
            api_resource = api_resource[0]

            resource_instance = api_resource.get(namespace=namespace)

            items = resource_instance.items
            for item in items:
                logger.debug(
                    f"{namespace=}: found {api_resource.group=} "
                    f"{api_resource.kind=} name={item.metadata.name}"
                )
                ignored = False
                for ignored_resource in ignored_resouces:
                    if (
                        api_resource.group == ignored_resource["apiGroup"]
                        and api_resource.kind == ignored_resource["kind"]
                        and re.match(ignored_resource["nameRegExp"], item.metadata.name)
                    ):
                        ignored = True
                        logger.debug(
                            f"{namespace=}: name={item.metadata.name} "
                            f"should be ignored"
                        )
                        break
                if not ignored:
                    logger.debug(f"{namespace=} is not empty")
                    return False
    return True
