targetScope = 'resourceGroup'
param location string = resourceGroup().location
@minLength(3)
@maxLength(40)
param prefix string
param sqlAdminObjectId string
param sqlAdminLogin string
param databaseName string = 'loyalty-demo'

resource sql 'Microsoft.Sql/servers@2023-08-01' = {
  name: '${prefix}-sql'
  location: location
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: sqlAdminLogin
      sid: sqlAdminObjectId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: true
    }
  }
}
resource database 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sql
  name: databaseName
  location: location
  sku: {name: 'Basic', tier: 'Basic', capacity: 5}
  properties: {maxSizeBytes: 2147483648}
}
resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: {addressPrefixes: ['10.84.0.0/24']}
    subnets: [
      {
        name: 'fabric-gateway'
        properties: {
          addressPrefix: '10.84.0.0/27'
          delegations: [{name: 'fabric', properties: {serviceName: 'Microsoft.PowerPlatform/vnetaccesslinks'}}]
          serviceEndpoints: [{service: 'Microsoft.Storage'}]
        }
      }
      {name: 'private-endpoints', properties: {addressPrefix: '10.84.0.32/27', privateEndpointNetworkPolicies: 'Disabled'}}
    ]
  }
}
resource endpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${prefix}-sql-pe'
  location: location
  properties: {
    subnet: {id: '${network.id}/subnets/private-endpoints'}
    privateLinkServiceConnections: [{name: 'sql', properties: {privateLinkServiceId: sql.id, groupIds: ['sqlServer']}}]
  }
}
resource zone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.database.windows.net'
  location: 'global'
}
resource link 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: zone
  name: '${prefix}-link'
  location: 'global'
  properties: {registrationEnabled: false, virtualNetwork: {id: network.id}}
}
resource dns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: endpoint
  name: 'sql'
  properties: {privateDnsZoneConfigs: [{name: 'sql', properties: {privateDnsZoneId: zone.id}}]}
}
output sqlServer string = sql.properties.fullyQualifiedDomainName
output sqlDatabase string = database.name
output gatewaySubnetId string = '${network.id}/subnets/fabric-gateway'
