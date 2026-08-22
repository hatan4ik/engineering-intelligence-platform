variable "location" {
  description = "Azure region for the reference deployment."
  type        = string
  default     = "eastus"
}

variable "search_sku" {
  description = "Azure AI Search SKU. Private endpoints require Basic or higher."
  type        = string
  default     = "basic"
}

variable "search_semantic_sku" {
  description = "Semantic search SKU for the reference search service."
  type        = string
  default     = "free"
}

variable "log_retention_days" {
  description = "Log Analytics retention period."
  type        = number
  default     = 30
}

variable "key_vault_purge_protection_enabled" {
  description = "Enable Key Vault purge protection. Use true for production."
  type        = bool
  default     = false
}

variable "workload_namespace" {
  description = "Kubernetes namespace containing the EIP workload service account."
  type        = string
  default     = "eip"
}

variable "workload_service_account" {
  description = "Kubernetes service account federated to the EIP user-assigned identity."
  type        = string
  default     = "eip-api"
}
