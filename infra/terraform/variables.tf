variable "location" {
  description = "Azure region for the integration or production-like deployment. Explicit selection is required."
  type        = string

  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "location must be explicitly set."
  }
}

variable "environment" {
  description = "Deployment environment classification used for resource tags and promotion controls."
  type        = string

  validation {
    condition     = contains(["integration", "production"], var.environment)
    error_message = "environment must be either integration or production."
  }
}

variable "aks_admin_group_object_ids" {
  description = "Entra group object IDs granted AKS administrative access. Local Kubernetes admin accounts stay disabled."
  type        = set(string)

  validation {
    condition     = length(var.aks_admin_group_object_ids) > 0
    error_message = "at least one Entra AKS administrator group must be explicitly configured."
  }
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

variable "temporal_postgresql_administrator_login" {
  description = "Bootstrap-only PostgreSQL administrator login. Temporal must use a separate least-privilege runtime user."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.temporal_postgresql_administrator_login))
    error_message = "temporal_postgresql_administrator_login must start with a lowercase letter and use lowercase letters, digits, or underscores."
  }
}

variable "temporal_postgresql_administrator_password" {
  description = "Bootstrap-only PostgreSQL administrator password supplied by the approved private deployment runner, never a checked-in tfvars file."
  type        = string
  sensitive   = true
  nullable    = false
}

variable "temporal_postgresql_primary_availability_zone" {
  description = "Availability zone for the Temporal PostgreSQL primary. Choose an Azure-supported zone in the selected region."
  type        = string

  validation {
    condition     = contains(["1", "2", "3"], var.temporal_postgresql_primary_availability_zone)
    error_message = "temporal_postgresql_primary_availability_zone must be 1, 2, or 3."
  }
}

variable "temporal_postgresql_standby_availability_zone" {
  description = "Different availability zone for the Temporal PostgreSQL standby."
  type        = string

  validation {
    condition     = contains(["1", "2", "3"], var.temporal_postgresql_standby_availability_zone)
    error_message = "temporal_postgresql_standby_availability_zone must be 1, 2, or 3."
  }
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
