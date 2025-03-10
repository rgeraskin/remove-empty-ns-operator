"""Tests for the remove-empty-ns-operator that manages empty Kubernetes namespaces."""

import signal
import time
import unittest

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException

DEADLINE_SECONDS = 30


class TestRemoveEmptyNsOperator(unittest.TestCase):
    """Test suite for the remove-empty-ns-operator functionality."""

    @classmethod
    def setUpClass(cls):
        # Load kube config
        try:
            config.load_kube_config()
        except ConfigException:
            config.load_incluster_config()

        cls.core_v1 = client.CoreV1Api()
        cls.apps_v1 = client.AppsV1Api()

        def handler(signum, frame):
            raise AssertionError("Deadline exceeded")

        signal.signal(signal.SIGALRM, handler)

        # Test constants
        cls.OPERATOR_ANNOTATION = "remove-empty-ns-operator.kopf.dev/will-remove"
        cls.finalizer = "kopf.zalando.org/KopfFinalizerMarker"
        cls.operator_name = "remove-empty-ns-operator"
        cls.operator_namespace = "remove-empty-ns-operator"
        cls.protected_namespace = "protected-one"

        # get the operator configmap
        configmap = cls.core_v1.read_namespaced_config_map(
            name=cls.operator_name, namespace=cls.operator_namespace
        )
        # decode configmap.data["settings.yaml"]) from yaml to dict
        cls.settings = yaml.safe_load(configmap.data["settings.yaml"])

    @classmethod
    def tearDownClass(cls):
        # restore the original settings
        cls.core_v1.patch_namespaced_config_map(
            name=cls.operator_name,
            namespace=cls.operator_namespace,
            body={"data": {"settings.yaml": yaml.dump(cls.settings)}},
        )

        # scale up the operator deployment
        cls.apps_v1.patch_namespaced_deployment_scale(
            name=cls.operator_name,
            namespace=cls.operator_namespace,
            body={"spec": {"replicas": 1}},
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ns_name = None

    def tearDown(self):
        """Clean up the test namespace if it still exists"""
        if self.ns_name:
            try:
                self.core_v1.delete_namespace(self.ns_name)
            except ApiException as e:
                if e.status != 404:  # Ignore if already deleted
                    raise

    def create_namespace(self, name):
        """Helper to create a namespace"""
        ns = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
        self.core_v1.create_namespace(ns)

    def create_deployment(self, namespace):
        """Helper to create a dummy deployment"""
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="dummy-deployment"),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": "dummy"}),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": "dummy"}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(name="nginx", image="nginx:latest")
                        ]
                    ),
                ),
            ),
        )
        return self.apps_v1.create_namespaced_deployment(
            namespace=namespace, body=deployment
        )

    def operator_restart(self):
        """Helper to restart the operator"""
        # scale down the operator deployment
        self.operator_scale_down()

        # scale up the operator deployment
        self.operator_scale_up()

    def operator_scale_down(self):
        """Helper to scale down the operator"""
        # scale down the operator deployment
        self.apps_v1.patch_namespaced_deployment_scale(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"spec": {"replicas": 0}},
        )

        # wait for operator to scale down
        signal.alarm(DEADLINE_SECONDS)
        while True:
            pods = self.core_v1.list_namespaced_pod(namespace=self.operator_namespace)
            if len(pods.items) == 0:
                break
            time.sleep(1)
        signal.alarm(0)

    def operator_scale_up(self):
        """Helper to scale up the operator"""
        # scale up the operator deployment
        self.apps_v1.patch_namespaced_deployment_scale(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"spec": {"replicas": 1}},
        )

        # wait for operator to start
        signal.alarm(DEADLINE_SECONDS)
        while True:
            pods = self.core_v1.list_namespaced_pod(namespace=self.operator_namespace)
            if len(pods.items) == 1 and pods.items[0].status.phase == "Running":
                break
            time.sleep(1)
        signal.alarm(0)

    def test_empty_namespace_gets_marked(self):
        """Test that an empty namespace gets marked for deletion"""
        # Create a new namespace
        self.ns_name = "test-empty-namespace-gets-marked"
        self.create_namespace(self.ns_name)

        # wait for operator to mark the namespace
        signal.alarm(DEADLINE_SECONDS)
        while True:
            ns = self.core_v1.read_namespace(self.ns_name)
            if (
                ns.metadata.annotations
                and self.OPERATOR_ANNOTATION in ns.metadata.annotations
                and ns.metadata.annotations[self.OPERATOR_ANNOTATION] == "True"
            ):
                break
            time.sleep(1)
        signal.alarm(0)

    def test_empty_namespace_gets_deleted(self):
        """Test that a marked empty namespace gets deleted"""
        # Create a new namespace
        self.ns_name = "test-empty-namespace-gets-deleted"
        self.create_namespace(self.ns_name)

        # wait for operator to delete the namespace
        signal.alarm(DEADLINE_SECONDS)
        while True:
            try:
                ns = self.core_v1.read_namespace(self.ns_name)
                if ns.metadata.deletion_timestamp:
                    break
            except ApiException as e:
                if e.status != 404:
                    break
            time.sleep(1)
        signal.alarm(0)

    def test_non_empty_namespace_not_marked(self):
        """Test that non-empty namespace doesn't get marked"""
        # Create a new namespace
        self.ns_name = "test-non-empty-namespace-not-marked"
        self.create_namespace(self.ns_name)

        # Create a deployment to make namespace non-empty
        self.create_deployment(self.ns_name)

        # Wait for operator check
        time.sleep(self.settings["interval"] * 2)

        # Verify namespace didn't get marked
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertNotIn(self.OPERATOR_ANNOTATION, ns.metadata.annotations or {})

    def test_marked_namespace_unmarked_when_resources_added(self):
        """Test that a marked namespace gets unmarked when resources are added"""
        # Create a new namespace
        self.ns_name = "test-marked-namespace-unmarked-when-resources-added"
        self.create_namespace(self.ns_name)

        # wait for operator to mark the namespace
        signal.alarm(DEADLINE_SECONDS)
        while True:
            ns = self.core_v1.read_namespace(self.ns_name)
            if (
                ns.metadata.annotations
                and self.OPERATOR_ANNOTATION in ns.metadata.annotations
                and ns.metadata.annotations[self.OPERATOR_ANNOTATION] == "True"
            ):
                break
            time.sleep(1)
        signal.alarm(0)

        # Add deployment
        self.create_deployment(self.ns_name)

        # wait for operator to unmark the namespace
        signal.alarm(DEADLINE_SECONDS)
        while True:
            ns = self.core_v1.read_namespace(self.ns_name)
            if (
                ns.metadata.annotations is None
                or self.OPERATOR_ANNOTATION not in ns.metadata.annotations
            ):
                break
            time.sleep(1)
        signal.alarm(0)

    def test_cleanup_finalizers(self):
        """Test that finalizers are cleaned up during operator shutdown"""
        # Ensure that cleanupFinalizers is enabled
        self.assertEqual(self.settings["cleanupFinalizers"], True)

        # Create a new namespace without finalizers
        ns1_name = "test-cleanup-finalizers"
        self.create_namespace(ns1_name)

        # Create a new namespace with additional finalizer
        ns2_name = "test-cleanup-finalizers-with-additional-finalizer"
        self.create_namespace(ns2_name)
        self.core_v1.patch_namespace(
            ns2_name, {"metadata": {"finalizers": ["dummy.dev/finalizer"]}}
        )

        # Create a deployment to make namespaces non-empty
        self.create_deployment(ns1_name)
        self.create_deployment(ns2_name)

        # Wait for operator to set finalizers
        signal.alarm(DEADLINE_SECONDS)
        while True:
            ns1 = self.core_v1.read_namespace(ns1_name)
            ns2 = self.core_v1.read_namespace(ns2_name)

            if (
                ns1.metadata.finalizers
                and ns2.metadata.finalizers
                and self.finalizer in ns1.metadata.finalizers
                and self.finalizer in ns2.metadata.finalizers
                and "dummy.dev/finalizer" in ns2.metadata.finalizers
            ):
                break
            time.sleep(1)
        signal.alarm(0)

        # scale down the operator deployment
        self.operator_scale_down()

        # check that finalizers are removed
        ns1 = self.core_v1.read_namespace(ns1_name)
        self.assertIsNone(ns1.metadata.finalizers)
        ns2 = self.core_v1.read_namespace(ns2_name)
        self.assertNotIn(self.finalizer, ns2.metadata.finalizers)

        # scale up the operator deployment
        self.operator_scale_up()

        # patch ns2 to remove dummy finalizer
        patch = [
            {
                "op": "remove",
                "path": "/metadata/finalizers",
            }
        ]
        self.core_v1.patch_namespace(ns2_name, patch)

        # remove namespaces
        self.core_v1.delete_namespace(ns1_name)
        self.core_v1.delete_namespace(ns2_name)

    def test_protected_namespace(self):
        """Test that protected namespaces are not deleted"""
        # ensure that protected namespace is in the list of protected namespaces
        self.assertIn(self.protected_namespace, self.settings["protectedNamespaces"])

        # create a protected namespace
        self.ns_name = self.protected_namespace
        self.create_namespace(self.ns_name)

        # wait for operator to check the namespace
        time.sleep(self.settings["interval"] * 3)

        # check that the namespace is not deleted
        namespaces = self.core_v1.list_namespace()
        self.assertIn(self.ns_name, [ns.metadata.name for ns in namespaces.items])
        # check that the namespace does not have the deletionTimestamp
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertIsNone(ns.metadata.deletion_timestamp)

    def test_dry_run(self):
        """Test that dry run mode works"""

        # patch configmap to enable dry run mode
        dry_run_settings = self.settings.copy()
        dry_run_settings["dryRun"] = True

        self.core_v1.patch_namespaced_config_map(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"data": {"settings.yaml": yaml.dump(dry_run_settings)}},
        )

        # restart the operator
        self.operator_restart()

        # create a new namespace
        self.ns_name = "test-dry-run"
        self.create_namespace(self.ns_name)

        # wait for operator to check the namespace
        time.sleep(self.settings["interval"] * 3)

        # check that the namespace is not deleted
        namespaces = self.core_v1.list_namespace()
        self.assertIn(self.ns_name, [ns.metadata.name for ns in namespaces.items])
        # check that the namespace does not have the deletionTimestamp
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertIsNone(ns.metadata.deletion_timestamp)

        # restore the original settings
        self.core_v1.patch_namespaced_config_map(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"data": {"settings.yaml": yaml.dump(self.settings)}},
        )

        # restart the operator
        self.operator_restart()


if __name__ == "__main__":
    unittest.main()
