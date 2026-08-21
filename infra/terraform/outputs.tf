output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.this.name
}

output "workload_identity_client_id" {
  description = "Client ID to set as azure.workload.identity/client-id on the EIP service account."
  value       = azurerm_user_assigned_identity.workload.client_id
}

output "azure_search_endpoint" {
  value = "https://${azurerm_search_service.this.name}.search.windows.net"
}

output "azure_openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "private_endpoint_subnet_id" {
  value = azurerm_subnet.private_endpoints.id
}
