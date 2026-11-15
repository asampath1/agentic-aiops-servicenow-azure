// Phase 1 of the live Azure demo: one Linux VM named like a CMDB CI, monitored by a Log Analytics
// workspace through the Azure Monitor Agent. Deployed at subscription scope so `what-if` works before
// the resource group exists. See infra/README.md for deploy / what-if / teardown.
targetScope = 'subscription'

@description('Azure region. Central India offers B2ats_v2 to free-trial subscriptions (non-zonal).')
param location string = 'centralindia'

@description('Region for the Automation account. Free-trial subscriptions may create Automation accounts only in eastus, eastus2, westus, northeurope, southeastasia, japanwest. Run Command works across regions.')
param automationLocation string = 'southeastasia'

@description('Resource group for every demo resource; `az group delete` on it is the teardown.')
param resourceGroupName string = 'rg-skr-aiops-demo'

@description('SSH public key for the VM admin user. Never used for login (no public IP; Run Command only).')
param adminSshPublicKey string

@description('VM size. B2ats_v2 = 2 vCPU / 1 GiB, free-tier eligible size family.')
param vmSize string = 'Standard_B2ats_v2'

@description('Daily auto-shutdown time (HHmm) and Windows time-zone id.')
param shutdownTime string = '2200'
param shutdownTimeZone string = 'India Standard Time'

@description('Monthly budget in the subscription currency. Alerts only; the free-trial spending limit is the hard stop.')
param budgetAmount int = 10

@description('Email for budget alerts. Leave empty to skip the budget.')
param budgetContactEmail string = ''

@description('First day of the current month (yyyy-MM-01); budgets must start on a month boundary.')
param budgetStartDate string = '${utcNow('yyyy-MM')}-01'

var tags = {
  project: 'agentic-aiops-servicenow-azure'
  dataset: 'SYNTH-SKR'
  purpose: 'demo'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module demo 'modules/demo.bicep' = {
  scope: rg
  name: 'skr-aiops-demo'
  params: {
    location: location
    tags: tags
    adminSshPublicKey: adminSshPublicKey
    vmSize: vmSize
    shutdownTime: shutdownTime
    shutdownTimeZone: shutdownTimeZone
  }
}

module automation 'modules/automation.bicep' = {
  scope: rg
  name: 'skr-aiops-automation'
  params: {
    location: automationLocation
    tags: tags
    workspaceResourceId: demo.outputs.workspaceResourceId
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (!empty(budgetContactEmail)) {
  name: 'budget-skr-aiops-demo'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [budgetContactEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [budgetContactEmail]
      }
    }
  }
}

output resourceGroup string = rg.name
output workspaceId string = demo.outputs.workspaceCustomerId
output workspaceResourceId string = demo.outputs.workspaceResourceId
output vmName string = demo.outputs.vmName
output automationAccount string = automation.outputs.automationAccountName
