terraform {
  required_version = ">= 1.8.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  name_suffix = random_string.suffix.result
  tags = {
    workload    = "engineering-intelligence-platform"
    environment = var.environment
    managed     = "terraform"
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-eip-${local.name_suffix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-eip"
  address_space       = ["10.40.0.0/16"]
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_subnet" "apps" {
  name                 = "snet-apps"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.40.1.0/24"]
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.40.2.0/23"]
}

resource "azurerm_subnet" "private_endpoints" {
  name                 = "snet-private-endpoints"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.40.4.0/24"]
}

# PostgreSQL Flexible Server uses VNet integration, which requires a dedicated
# delegated subnet rather than a Private Endpoint subnet.
resource "azurerm_subnet" "temporal_postgresql" {
  name                 = "snet-temporal-postgresql"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.40.5.0/28"]

  delegation {
    name = "postgresql-flexible-server"

    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "law-eip-${local.name_suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.tags
}

# Retrieval projection. API-key authentication and public ingress are disabled;
# callers authenticate with Entra ID and reach the service through Private Link.
resource "azurerm_search_service" "this" {
  name                          = "srch-eip-${local.name_suffix}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  sku                           = var.search_sku
  public_network_access_enabled = false
  local_authentication_enabled  = false
  network_rule_bypass_option    = "None"
  semantic_search_sku           = var.search_semantic_sku

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

# Enterprise model endpoint. A custom subdomain is required for Entra token auth
# and Private Endpoint attachment.
resource "azurerm_cognitive_account" "openai" {
  name                               = "aoai-eip-${local.name_suffix}"
  location                           = azurerm_resource_group.this.location
  resource_group_name                = azurerm_resource_group.this.name
  kind                               = "OpenAI"
  sku_name                           = "S0"
  custom_subdomain_name              = "aoai-eip-${local.name_suffix}"
  public_network_access_enabled      = false
  outbound_network_access_restricted = true

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

resource "azurerm_key_vault" "this" {
  name                          = "kveip${local.name_suffix}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  public_network_access_enabled = false
  soft_delete_retention_days    = 90
  purge_protection_enabled      = true
  tags                          = local.tags
}

# Private DNS zones used by clients inside the EIP VNet. Clients continue to use
# normal service FQDNs; Azure DNS resolves their Private Link CNAMEs privately.
resource "azurerm_private_dns_zone" "search" {
  name                = "privatelink.search.windows.net"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone" "key_vault" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone" "temporal_postgresql" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "search" {
  name                  = "link-search-eip"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.search.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai" {
  name                  = "link-openai-eip"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "key_vault" {
  name                  = "link-kv-eip"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.key_vault.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "azurerm_private_dns_zone_virtual_network_link" "temporal_postgresql" {
  name                  = "link-temporal-postgresql-eip"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.temporal_postgresql.name
  virtual_network_id    = azurerm_virtual_network.this.id
}

resource "azurerm_private_endpoint" "search" {
  name                = "pe-search-eip"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-search-eip"
    private_connection_resource_id = azurerm_search_service.this.id
    subresource_names              = ["searchService"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "search"
    private_dns_zone_ids = [azurerm_private_dns_zone.search.id]
  }
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-openai-eip"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-openai-eip"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "openai"
    private_dns_zone_ids = [azurerm_private_dns_zone.openai.id]
  }
}

resource "azurerm_private_endpoint" "key_vault" {
  name                = "pe-kv-eip"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "psc-kv-eip"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "key-vault"
    private_dns_zone_ids = [azurerm_private_dns_zone.key_vault.id]
  }
}

# Temporal is stateful infrastructure. Its PostgreSQL persistence uses private
# VNet integration, zone redundancy, TLS, and long backup retention. Schema
# migration and least-privilege database-user creation are explicit release
# prerequisites; the normal Temporal server chart does neither automatically.
resource "azurerm_postgresql_flexible_server" "temporal" {
  name                          = "pg-temporal-eip-${local.name_suffix}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  administrator_login           = var.temporal_postgresql_administrator_login
  administrator_password        = var.temporal_postgresql_administrator_password
  sku_name                      = "GP_Standard_D2ds_v5"
  storage_mb                    = 32768
  backup_retention_days         = 35
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = false
  delegated_subnet_id           = azurerm_subnet.temporal_postgresql.id
  private_dns_zone_id           = azurerm_private_dns_zone.temporal_postgresql.id
  zone                          = var.temporal_postgresql_primary_availability_zone

  high_availability {
    mode                      = "ZoneRedundant"
    standby_availability_zone = var.temporal_postgresql_standby_availability_zone
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.temporal_postgresql]
  tags       = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "temporal" {
  name      = "temporal"
  server_id = azurerm_postgresql_flexible_server.temporal.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_database" "temporal_visibility" {
  name      = "temporal_visibility"
  server_id = azurerm_postgresql_flexible_server.temporal.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_user_assigned_identity" "workload" {
  name                = "id-eip-workload-${local.name_suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = "aks-eip-${local.name_suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  dns_prefix          = "eip"

  identity {
    type = "SystemAssigned"
  }

  oidc_issuer_enabled                 = true
  workload_identity_enabled           = true
  private_cluster_enabled             = true
  private_dns_zone_id                 = "System"
  private_cluster_public_fqdn_enabled = false
  role_based_access_control_enabled   = true
  local_account_disabled              = true
  azure_policy_enabled                = true
  run_command_enabled                 = false
  sku_tier                            = "Standard"

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled     = true
    tenant_id              = data.azurerm_client_config.current.tenant_id
    admin_group_object_ids = var.aks_admin_group_object_ids
  }

  default_node_pool {
    name           = "system"
    vm_size        = "Standard_D4ds_v5"
    vnet_subnet_id = azurerm_subnet.aks.id
    node_count     = 2
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  }

  network_profile {
    network_plugin = "azure"
    network_policy = "azure"
  }

  tags = local.tags
}

resource "azurerm_federated_identity_credential" "workload" {
  name                = "fic-eip-api"
  resource_group_name = azurerm_resource_group.this.name
  parent_id           = azurerm_user_assigned_identity.workload.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.this.oidc_issuer_url
  subject             = "system:serviceaccount:${var.workload_namespace}:${var.workload_service_account}"
}

# Least-privilege runtime data-plane roles. Index creation/administration should
# be performed by a separate deployment identity, not the application runtime.
resource "azurerm_role_assignment" "search_reader" {
  scope                = azurerm_search_service.this.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

resource "azurerm_role_assignment" "openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}

resource "azurerm_role_assignment" "key_vault_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
}
