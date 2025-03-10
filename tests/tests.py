"""Tests for the remove-empty-ns-operator that manages empty Kubernetes namespaces."""

import time
import unittest

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ns_name = None

    def tearDown(self):
        """Clean up the test namespace if it still exists"""
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


if __name__ == "__main__":
    unittest.main()
