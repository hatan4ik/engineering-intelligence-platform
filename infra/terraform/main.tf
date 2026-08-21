terraform {
  required_version = ">= 1.8.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "azurerm" { features {} }

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_resource_group" "this" {
  name     = "rg-eip-${random_string.suffix.result}"
  location = var.location
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-eip"
  address_space       = ["10.40.0.0/16"]
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
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

resource "azurerm_log_analytics_workspace" "this" {
  name                = "law-eip-${random_string.suffix.result}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_search_service" "this" {
  name                = "srch-eip-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "basic"
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = "aks-eip-${random_string.suffix.result}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  dns_prefix          = "eip"

  identity { type = "SystemAssigned" }

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
}
