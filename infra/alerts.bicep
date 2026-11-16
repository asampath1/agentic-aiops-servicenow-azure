// Phase 3: Azure Monitor alerts on the demo VM -> action group -> Logic App -> ServiceNow incident.
// Separate deployment (resource-group scope) because it needs the ServiceNow credentials:
//   az deployment group create -g rg-skr-aiops-demo -n skr-aiops-alerts -f infra/alerts.bicep \
//     -p snInstance="$SN_INSTANCE" snUser="$SN_USER" snPassword="$SN_PASSWORD"
// Incidents are tagged correlation_id=SYNTH-SKR-LIVE so they never join the 24-incident eval set.

param location string = resourceGroup().location

@description('ServiceNow instance name, e.g. dev123456 (not the full URL).')
param snInstance string

@description('ServiceNow API user (the PDI service account).')
param snUser string

@secure()
@description('ServiceNow API password. Stored as a SecureString Logic App parameter; never in source control.')
param snPassword string

param vmName string = 'vm-orders-app-01'
param correlationTag string = 'SYNTH-SKR-LIVE'

@description('Automation account whose job history decides whether a cleared alert was actually remediated.')
param automationAccountName string = 'aa-skr-aiops'

@description('Close code set when an incident is auto-resolved (added by infra/servicenow/add_close_code.py).')
param closeCodeValue string = 'Auto-remediated (AIOps)'

var tags = {
  project: 'agentic-aiops-servicenow-azure'
  dataset: 'SYNTH-SKR'
  purpose: 'demo'
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' existing = {
  name: vmName
}

resource aa 'Microsoft.Automation/automationAccounts@2023-11-01' existing = {
  name: automationAccountName
}

// ---------------------------------------------------------------- Logic App: alert -> ServiceNow
resource la 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'la-skr-alert-to-snow'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned' // reads the Automation job history (Reader on that account only)
  }
  properties: {
    state: 'Enabled'
    definition: loadJsonContent('logicapp/alert-to-servicenow.json')
    parameters: {
      snInstance: { value: snInstance }
      snUser: { value: snUser }
      snPassword: { value: snPassword }
      correlationTag: { value: correlationTag }
      automationAccountId: { value: aa.id }
      closeCodeValue: { value: closeCodeValue }
    }
  }
}

// Read-only on the Automation account: list jobs and read their status/parameters. Cannot start jobs.
resource laReadsJobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aa.id, la.id, 'reader')
  scope: aa
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7') // Reader
    principalId: la.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource ag 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-skr-servicenow'
  location: 'Global'
  tags: tags
  properties: {
    groupShortName: 'skr-snow'
    enabled: true
    logicAppReceivers: [
      {
        name: 'alert-to-servicenow'
        resourceId: la.id
        callbackUrl: listCallbackUrl('${la.id}/triggers/manual', '2019-05-01').value
        useCommonAlertSchema: true
      }
    ]
  }
}

// ---------------------------------------------------------------- Alert rules (names as in the KB history)
resource cpuHigh 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'vm-cpu-high'
  location: 'global'
  tags: tags
  properties: {
    description: 'Percentage CPU > 90% on ${vmName} for 15 min'
    severity: 2
    enabled: true
    scopes: [vm.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT15M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'cpu'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.Compute/virtualMachines'
          metricName: 'Percentage CPU'
          operator: 'GreaterThan'
          threshold: 90
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [
      {
        actionGroupId: ag.id
      }
    ]
  }
}

resource diskLow 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'vm-disk-low'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    description: 'Logical disk free space < 10% on ${vmName} (/)'
    severity: 2
    enabled: true
    scopes: [vm.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT10M'
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: 'Perf | where ObjectName == "Logical Disk" and CounterName == "% Free Space" and InstanceName == "/"'
          timeAggregation: 'Average'
          metricMeasureColumn: 'CounterValue'
          operator: 'LessThan'
          threshold: 10
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [ag.id]
    }
  }
}

output logicApp string = la.name
output actionGroup string = ag.name
