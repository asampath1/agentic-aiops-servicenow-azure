// Resource-group resources for the live demo (Phase 1): workspace, network, VM, Azure Monitor Agent,
// data collection rule, auto-shutdown.

param location string
param tags object
param adminSshPublicKey string
param vmSize string
param shutdownTime string
param shutdownTimeZone string

@description('Named after a CMDB CI so ServiceNow incidents, KB history and runbook targets line up.')
param vmName string = 'vm-orders-app-01'

param adminUsername string = 'skradmin'

// ---------------------------------------------------------------- Log Analytics
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-skr-aiops'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json('0.15') // ~4.5 GB/month: stays inside the free ingestion allowance
    }
  }
}

// ---------------------------------------------------------------- Network (no public IP, no inbound)
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-snet-vms'
  location: location
  tags: tags
  properties: {
    securityRules: [] // default rules only: no inbound from the internet
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-skr-demo'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.20.0.0/24']
    }
    subnets: [
      {
        name: 'snet-vms'
        properties: {
          addressPrefix: '10.20.0.0/26'
          networkSecurityGroup: {
            id: nsg.id
          }
          // New subnets are private by default; the agent and apt need outbound internet.
          // Default outbound access avoids a NAT gateway (which is billed hourly).
          defaultOutboundAccess: true
        }
      }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-${vmName}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vnet.properties.subnets[0].id
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

// ---------------------------------------------------------------- VM
resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: vmName
  location: location
  tags: union(tags, {
    cmdb_ci: vmName
  })
  identity: {
    type: 'SystemAssigned' // used by the Azure Monitor Agent
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminSshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-${vmName}'
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: {
          storageAccountType: 'Premium_LRS' // 64 GB = P6, the managed-disk size in the free-tier list
        }
        deleteOption: 'Delete'
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            deleteOption: 'Delete'
          }
        }
      ]
    }
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true // managed boot diagnostics storage, no storage account needed
      }
    }
  }
}

resource ama 'Microsoft.Compute/virtualMachines/extensions@2024-07-01' = {
  parent: vm
  name: 'AzureMonitorLinuxAgent'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.Monitor'
    type: 'AzureMonitorLinuxAgent'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    enableAutomaticUpgrade: true
  }
}

// ---------------------------------------------------------------- What the Diagnostics agent queries
// Perf (CPU, memory, disk) + Syslog. Heartbeat is sent automatically once the DCR is associated.
resource dcr 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: 'dcr-skr-linux-vms'
  location: location
  tags: tags
  kind: 'Linux'
  properties: {
    dataSources: {
      performanceCounters: [
        {
          name: 'perfCounters'
          streams: ['Microsoft-Perf']
          samplingFrequencyInSeconds: 60
          counterSpecifiers: [
            '\\Processor(*)\\% Processor Time'
            '\\Memory(*)\\Available MBytes Memory'
            '\\Memory(*)\\% Available Memory'
            '\\Logical Disk(*)\\% Free Space'
            '\\Logical Disk(*)\\Free Megabytes'
          ]
        }
      ]
      syslog: [
        {
          name: 'syslog'
          streams: ['Microsoft-Syslog']
          facilityNames: ['daemon', 'syslog', 'user']
          logLevels: ['Warning', 'Error', 'Critical', 'Alert', 'Emergency']
        }
      ]
    }
    destinations: {
      logAnalytics: [
        {
          name: 'law'
          workspaceResourceId: law.id
        }
      ]
    }
    dataFlows: [
      {
        streams: ['Microsoft-Perf', 'Microsoft-Syslog']
        destinations: ['law']
      }
    ]
  }
}

resource dcrAssociation 'Microsoft.Insights/dataCollectionRuleAssociations@2023-03-11' = {
  name: 'dcra-${vmName}'
  scope: vm
  properties: {
    dataCollectionRuleId: dcr.id
  }
  dependsOn: [ama]
}

// ---------------------------------------------------------------- Cost control
resource shutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = {
  name: 'shutdown-computevm-${vmName}'
  location: location
  tags: tags
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: {
      time: shutdownTime
    }
    timeZoneId: shutdownTimeZone
    targetResourceId: vm.id
    notificationSettings: {
      status: 'Disabled'
    }
  }
}

output workspaceCustomerId string = law.properties.customerId
output workspaceResourceId string = law.id
output vmName string = vm.name
