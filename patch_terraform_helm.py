import re

filepath = 'infra/terraform/main.tf'
with open(filepath, 'r') as f:
    content = f.read()

helm_config = """
provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.this.kube_config.0.host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.cluster_ca_certificate)
  }
}

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.this.kube_config.0.host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.this.kube_config.0.cluster_ca_certificate)
}

resource "kubernetes_namespace" "eip" {
  metadata {
    name = var.workload_namespace
  }
  depends_on = [azurerm_kubernetes_cluster.this]
}

resource "kubernetes_namespace" "temporal" {
  metadata {
    name = "temporal"
  }
  depends_on = [azurerm_kubernetes_cluster.this]
}

resource "helm_release" "temporal" {
  name       = "temporal"
  repository = "https://go.temporal.io/helm-charts"
  chart      = "temporal"
  namespace  = kubernetes_namespace.temporal.metadata[0].name
  version    = "0.23.0" # Use an appropriate chart version

  set {
    name  = "server.replicaCount"
    value = "1"
  }
  
  set {
    name  = "cassandra.config.setup.enabled"
    value = "false"
  }
  
  set {
    name  = "mysql.config.setup.enabled"
    value = "false"
  }

  set {
    name  = "postgresql.config.setup.enabled"
    value = "true"
  }

  set {
    name  = "postgresql.host"
    value = azurerm_postgresql_flexible_server.temporal.fqdn
  }
  
  set {
    name  = "postgresql.port"
    value = "5432"
  }

  set {
    name  = "postgresql.user"
    value = var.temporal_postgresql_administrator_login
  }

  set {
    name  = "postgresql.password"
    value = var.temporal_postgresql_administrator_password
  }

  depends_on = [
    azurerm_kubernetes_cluster.this,
    azurerm_postgresql_flexible_server_database.temporal,
    azurerm_postgresql_flexible_server_database.temporal_visibility
  ]
}

resource "helm_release" "eip" {
  name      = "eip"
  chart     = "${path.module}/../../helm/eip"
  namespace = kubernetes_namespace.eip.metadata[0].name

  set {
    name  = "env.AZURE_CLIENT_ID"
    value = azurerm_user_assigned_identity.workload.client_id
  }
  
  set {
    name  = "env.TEMPORAL_HOST"
    value = "temporal-frontend.temporal.svc.cluster.local:7233"
  }

  depends_on = [
    helm_release.temporal
  ]
}
"""

content += helm_config

with open(filepath, 'w') as f:
    f.write(content)
