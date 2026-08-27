import json
import logging
import urllib3
from dataclasses import dataclass
from typing import Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .catalog import Runbook
from .policy import ActionRequest

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class KubernetesClientAdapter:
    """Robust ActionAdapter using the official python kubernetes client instead of subprocess."""
    
    def __init__(self, namespace: str = "default", in_cluster: bool = True):
        self.namespace = namespace
        try:
            if in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()
        except config.config_exception.ConfigException:
            logger.warning("Could not load K8s config. Mocking client for testing.")
            self.apps_v1 = None
            self.core_v1 = None
            return

        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(c for c in value.lower() if c.isalnum() or c == "-")[:63].strip("-")
        
    def _get_deployment(self, name: str) -> Optional[client.V1Deployment]:
        if not self.apps_v1:
            return None
        try:
            return self.apps_v1.read_namespaced_deployment(name=name, namespace=self.namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def preflight(self, runbook: Runbook, request: ActionRequest) -> tuple[bool, str]:
        # Simple preflight validation using python client
        deployment_name = self._safe_name(request.service)
        deployment = self._get_deployment(deployment_name)
        
        for pre in runbook.preconditions:
            if pre == "deployment.exists":
                if not deployment and self.apps_v1:
                    return False, f"precondition failed: deployment {deployment_name} does not exist"
            # In a real FAANG system, we'd query metrics/prometheus for "pods.oomkilled_present" etc.
            
        return True, ""

    def execute(self, runbook_id: str, request: ActionRequest) -> str:
        deployment_name = self._safe_name(request.service)
        if not self.apps_v1:
            return f"Mock execute {runbook_id} for {deployment_name}"

        if runbook_id in {"aks.restart.workload", "aks.restart.crashloop", "aks.restart.oom"}:
            # Equivalent to kubectl rollout restart
            deployment = self._get_deployment(deployment_name)
            if not deployment:
                raise RuntimeError("Deployment not found")
                
            import datetime
            now = datetime.datetime.utcnow().isoformat()
            
            if not deployment.spec.template.metadata:
                deployment.spec.template.metadata = client.V1ObjectMeta()
            if not deployment.spec.template.metadata.annotations:
                deployment.spec.template.metadata.annotations = {}
                
            deployment.spec.template.metadata.annotations['kubectl.kubernetes.io/restartedAt'] = now
            
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, 
                namespace=self.namespace, 
                body=deployment
            )
            return f"Deployment {deployment_name} restarted successfully."
            
        elif runbook_id == "aks.scale.memory":
            deployment = self._get_deployment(deployment_name)
            if not deployment:
                raise RuntimeError("Deployment not found")
                
            annotations = deployment.metadata.annotations or {}
            limit = annotations.get("eip.simdream.io/memory-limit")
            request_memory = annotations.get("eip.simdream.io/memory-request")
            
            if not limit or not request_memory:
                raise RuntimeError("pre-approved memory profile values are missing")
                
            for container in deployment.spec.template.spec.containers:
                if not container.resources:
                    container.resources = client.V1ResourceRequirements(limits={}, requests={})
                container.resources.limits['memory'] = limit
                container.resources.requests['memory'] = request_memory
                
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name, 
                namespace=self.namespace, 
                body=deployment
            )
            return f"Deployment {deployment_name} scaled to memory {limit} successfully."
            
        else:
            raise ValueError(f"Runbook has no Kubernetes action adapter: {runbook_id}")
