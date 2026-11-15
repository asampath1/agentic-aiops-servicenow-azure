// Phase 2: Azure Automation account that runs the KB's *safe* runbooks against the demo VM.
// Only runbooks the KB marks "safe to run automatically" are created here; manual ones never are.
// Runbook bodies are uploaded and published by infra/publish-runbooks.sh (Bicep cannot inline them).

param location string
param tags object
param workspaceResourceId string

param automationAccountName string = 'aa-skr-aiops'

@description('Safe runbooks (names must match the KB articles and the agents\' RB-* ids).')
param runbooks array = [
  {
    name: 'RB-VM-Restart-Service'
    description: 'KB "Troubleshooting high CPU on Azure VMs": restart the named service / stop the runaway process (Linux).'
  }
  {
    name: 'RB-VM-Cleanup-Disk'
    description: 'KB "Resolving low disk space on Azure VMs": vacuum journal, clean apt cache, truncate oversized app logs (Linux).'
  }
]

resource aa 'Microsoft.Automation/automationAccounts@2023-11-01' = {
  name: automationAccountName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    sku: {
      name: 'Basic'
    }
    publicNetworkAccess: true
    disableLocalAuth: true // no webhooks / shared keys: jobs start only through ARM with Entra ID auth
  }
}

resource rb 'Microsoft.Automation/automationAccounts/runbooks@2023-11-01' = [for r in runbooks: {
  parent: aa
  name: r.name
  location: location
  tags: tags
  properties: {
    runbookType: 'PowerShell72'
    description: r.description
    logProgress: false
    logVerbose: false
  }
}]

// Runbooks look up the VM in this resource group (the identity has no subscription-wide read).
resource targetRg 'Microsoft.Automation/automationAccounts/variables@2023-11-01' = {
  parent: aa
  name: 'TargetResourceGroup'
  properties: {
    value: '"${resourceGroup().name}"'
    isEncrypted: false
    description: 'Resource group holding the VMs the runbooks may act on.'
  }
}

// Least privilege: read VMs + Run Command, nothing else (no start/stop/delete/resize), this RG only.
resource operatorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'skr-runbook-operator')
  properties: {
    roleName: 'SKR Runbook Operator (${resourceGroup().name})'
    description: 'Lets the SKR Automation account read VMs and run commands on them. Nothing else.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [
      {
        actions: [
          'Microsoft.Compute/virtualMachines/read'
          'Microsoft.Compute/virtualMachines/instanceView/read'
          'Microsoft.Compute/virtualMachines/runCommand/action'
        ]
        notActions: []
      }
    ]
  }
}

resource operatorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, aa.id, operatorRole.id)
  properties: {
    roleDefinitionId: operatorRole.id
    principalId: aa.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Job status and output in the workspace, next to the VM telemetry.
resource aaDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-law-skr-aiops'
  scope: aa
  properties: {
    workspaceId: workspaceResourceId
    logs: [
      {
        category: 'JobLogs'
        enabled: true
      }
      {
        category: 'JobStreams'
        enabled: true
      }
    ]
  }
}

output automationAccountName string = aa.name
output principalId string = aa.identity.principalId
