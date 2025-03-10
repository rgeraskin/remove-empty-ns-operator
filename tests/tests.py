"""Tests for the remove-empty-ns-operator that manages empty Kubernetes namespaces."""

# 2do: replace time.sleep with something more elegant

import time
import unittest

import yaml
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException


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

        # Test constants
        cls.TEST_NS_PREFIX = "test-empty-ns-"
        cls.OPERATOR_ANNOTATION = "remove-empty-ns-operator.kopf.dev/will-remove"
        cls.check_interval = 5
        cls.finalizer = "kopf.zalando.org/KopfFinalizerMarker"
        cls.operator_name = "remove-empty-ns-operator"
        cls.operator_namespace = "remove-empty-ns-operator"

        # get the operator configmap
        configmap = cls.core_v1.read_namespaced_config_map(
            name=cls.operator_name, namespace=cls.operator_namespace
        )
        # decode configmap.data["settings.yaml"]) from yaml to dict
        cls.settings = yaml.safe_load(configmap.data["settings.yaml"])

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

    def test_empty_namespace_gets_marked(self):
        """Test that an empty namespace gets marked for deletion"""
        # Create a new namespace
        self.ns_name = "test-empty-namespace-gets-marked"
        self.create_namespace(self.ns_name)

        # Wait for operator to check the namespace
        time.sleep(self.check_interval + 5)

        # Verify the namespace got marked
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertIn(self.OPERATOR_ANNOTATION, ns.metadata.annotations)
        self.assertEqual(ns.metadata.annotations[self.OPERATOR_ANNOTATION], "True")

    def test_empty_namespace_gets_deleted(self):
        """Test that a marked empty namespace gets deleted"""
        # Create a new namespace
        self.ns_name = "test-empty-namespace-gets-deleted"
        self.create_namespace(self.ns_name)

        # Wait for two intervals - one to mark, one to delete,
        # and 5 seconds to ensure the operator has time to delete the namespace
        time.sleep((self.check_interval * 2) + 5 + 5)

        # Verify the namespace was deleted
        with self.assertRaises(ApiException) as context:
            self.core_v1.read_namespace(self.ns_name)
        self.assertEqual(context.exception.status, 404)

    def test_non_empty_namespace_not_marked(self):
        """Test that non-empty namespace doesn't get marked"""
        # Create a new namespace
        self.ns_name = "test-non-empty-namespace-not-marked"
        self.create_namespace(self.ns_name)

        # Create a deployment to make namespace non-empty
        self.create_deployment(self.ns_name)

        # Wait for operator check
        time.sleep(self.check_interval + 5)

        # Verify namespace didn't get marked
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertNotIn(self.OPERATOR_ANNOTATION, ns.metadata.annotations or {})

    def test_marked_namespace_unmarked_when_resources_added(self):
        """Test that a marked namespace gets unmarked when resources are added"""
        # Create a new namespace
        self.ns_name = "test-marked-namespace-unmarked-when-resources-added"
        self.create_namespace(self.ns_name)

        # Wait for namespace to get marked
        time.sleep(self.check_interval + 5)

        # Verify it's marked
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertIn(self.OPERATOR_ANNOTATION, ns.metadata.annotations)

        # Add deployment
        self.create_deployment(self.ns_name)

        # Wait for next check
        time.sleep(self.check_interval + 5)

        # Verify mark was removed
        ns = self.core_v1.read_namespace(self.ns_name)
        self.assertNotIn(self.OPERATOR_ANNOTATION, ns.metadata.annotations or {})

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

        # Wait for operator to check the namespace
        time.sleep(self.check_interval + 5)

        # check that finalizers are set
        ns1 = self.core_v1.read_namespace(ns1_name)
        self.assertIn(self.finalizer, ns1.metadata.finalizers)
        ns2 = self.core_v1.read_namespace(ns2_name)
        self.assertIn(self.finalizer, ns2.metadata.finalizers)
        self.assertIn("dummy.dev/finalizer", ns2.metadata.finalizers)

        # scale down the operator deployment
        self.apps_v1.patch_namespaced_deployment_scale(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"spec": {"replicas": 0}},
        )

        # wait for operator to shutdown
        time.sleep(5)

        # check that finalizers are removed
        ns1 = self.core_v1.read_namespace(ns1_name)
        self.assertIsNone(ns1.metadata.finalizers)
        ns2 = self.core_v1.read_namespace(ns2_name)
        self.assertNotIn(self.finalizer, ns2.metadata.finalizers)

        # scale up the operator deployment
        self.apps_v1.patch_namespaced_deployment_scale(
            name=self.operator_name,
            namespace=self.operator_namespace,
            body={"spec": {"replicas": 1}},
        )

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

if __name__ == "__main__":
    unittest.main()
