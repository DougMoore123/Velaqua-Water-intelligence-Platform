@description('Deployment location')
param location string = resourceGroup().location

@description('Environment prefix for globally unique names where required')
param namePrefix string = 'waterintel'

@description('Storage account SKU')
param storageSku string = 'Standard_LRS'

@description('Azure ML workspace name')
param amlWorkspaceName string = '${namePrefix}-aml'

@description('Azure Databricks workspace name')
param databricksWorkspaceName string = '${namePrefix}-dbx'

@description('Key Vault name')
param keyVaultName string = '${namePrefix}-kv'

@description('Event Hub namespace name')
param eventHubNamespaceName string = '${namePrefix}-evhns'

@description('Event Hub name for telemetry stream')
param eventHubName string = 'telemetry-ingest'

@description('AI Search service name')
param searchServiceName string = '${namePrefix}-search'

@description('Application Insights name')
param appInsightsName string = '${namePrefix}-appi'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: toLower('${namePrefix}st${uniqueString(resourceGroup().id)}')
  location: location
  sku: {
    name: storageSku
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'raw'
}

resource bronzeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'bronze'
}

resource silverContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'silver'
}

resource goldContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'gold'
}

resource adf 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: '${namePrefix}-adf'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource evhNamespace 'Microsoft.EventHub/namespaces@2023-01-01-preview' = {
  name: eventHubNamespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource evh 'Microsoft.EventHub/namespaces/eventhubs@2023-01-01-preview' = {
  parent: evhNamespace
  name: eventHubName
  properties: {
    messageRetentionInDays: 3
    partitionCount: 4
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    publicNetworkAccess: 'Enabled'
  }
}

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'basic'
  }
  properties: {
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
}

resource databricks 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: databricksWorkspaceName
  location: location
  sku: {
    name: 'standard'
  }
  properties: {
    managedResourceGroupId: resourceGroup().id
    publicNetworkAccess: 'Enabled'
  }
}

resource aml 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: amlWorkspaceName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    applicationInsights: appi.id
    keyVault: kv.id
    storageAccount: storage.id
    publicNetworkAccess: 'Enabled'
  }
}

output storageAccountName string = storage.name
output dataFactoryName string = adf.name
output eventHubNamespace string = evhNamespace.name
output eventHubName string = evh.name
output amlWorkspace string = aml.name
output databricksWorkspace string = databricks.name
output searchService string = search.name
