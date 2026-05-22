# schedule_task.ps1
# Automates registering, disabling, enabling, removing, or running the Mutual Fund Pipeline task.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Register     (Registers or overwrites the daily schedule at 6:00 AM)
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Disable      (Temporarily disables the scheduled task - turn OFF)
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Enable       (Re-enables the scheduled task - turn ON)
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Unregister   (Completely deletes/removes the scheduled task)
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Status       (Checks the current state of the scheduled task)
#   powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Run          (Forces the scheduled task to run immediately for testing)

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Register", "Disable", "Enable", "Unregister", "Status", "Run")]
    [string]$Action = "Register"
)

$TaskName = "Mutual_Fund_Dashboard_Pipeline"
$Description = "Daily mutual fund data ingestion, cleaning, and performance metrics calculation."
$ScriptPath = Join-Path $PSScriptRoot "run_pipeline.bat"

function Get-TaskState {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        return $task.State
    }
    return $null
}

switch ($Action) {
    "Register" {
        # Trigger: daily at 6:00 AM
        $Trigger = New-ScheduledTaskTrigger -Daily -At "6:00 AM"

        # Action: Execute the run_pipeline.bat wrapper
        $TaskAction = New-ScheduledTaskAction -Execute $ScriptPath -WorkingDirectory $PSScriptRoot

        # Settings
        $Settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -WakeToRun `
            -RunOnlyIfNetworkAvailable `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1)

        # Remove existing task if present to avoid conflicts
        if (Get-TaskState) {
            Write-Host "Existing scheduled task '$TaskName' found. Overwriting..."
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }

        # Register task
        Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $Trigger -Settings $Settings -Description $Description | Out-Null

        Write-Host "--------------------------------------------------------"
        Write-Host "SUCCESS: Windows Task Scheduler Task registered successfully!"
        Write-Host "Task Name   : $TaskName"
        Write-Host "Trigger     : Daily at $($info.NextRunTime)"
        Write-Host "Action      : $ScriptPath"
        Write-Host "Working Dir : $PSScriptRoot"
        Write-Host "Status      : Active (Enabled)"
        Write-Host "--------------------------------------------------------"
        Write-Host "To temporarily disable it (turn OFF):"
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Disable"
        Write-Host ""
        Write-Host "To completely remove it:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Unregister"
        Write-Host ""
        Write-Host "To run it manually now:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File .\schedule_task.ps1 -Action Run"
    }

    "Disable" {
        $state = Get-TaskState
        if ($null -eq $state) {
            Write-Host "[WARN] Task '$TaskName' is not registered. Nothing to disable." -ForegroundColor Yellow
        }
        else {
            Disable-ScheduledTask -TaskName $TaskName | Out-Null
            Write-Host "SUCCESS: Task '$TaskName' has been DISABLED (turned OFF)." -ForegroundColor Green
        }
    }

    "Enable" {
        $state = Get-TaskState
        if ($null -eq $state) {
            Write-Host "[ERROR] Task '$TaskName' is not registered. Cannot enable." -ForegroundColor Red
        }
        else {
            Enable-ScheduledTask -TaskName $TaskName | Out-Null
            Write-Host "SUCCESS: Task '$TaskName' has been ENABLED (turned ON)." -ForegroundColor Green
        }
    }

    "Unregister" {
        $state = Get-TaskState
        if ($null -eq $state) {
            Write-Host "[WARN] Task '$TaskName' is not registered. Nothing to remove." -ForegroundColor Yellow
        }
        else {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "SUCCESS: Task '$TaskName' has been completely REMOVED." -ForegroundColor Green
        }
    }

    "Status" {
        $state = Get-TaskState
        if ($null -eq $state) {
            Write-Host "Task '$TaskName' is NOT registered." -ForegroundColor Yellow
        }
        else {
            Write-Host "Task '$TaskName' status: $state" -ForegroundColor Green
            $info = Get-ScheduledTaskInfo -TaskName $TaskName
            if ($info.LastRunTime) {
                Write-Host "  Last Run Time  : $($info.LastRunTime)"
                Write-Host "  Last Run Result: 0x$($info.LastTaskResult.ToString('X8'))"
            }
            if ($info.NextRunTime) {
                Write-Host "  Next Run Time  : $($info.NextRunTime)"
            }
        }
    }

    "Run" {
        $state = Get-TaskState
        if ($null -eq $state) {
            Write-Host "[ERROR] Task '$TaskName' is not registered. Cannot run." -ForegroundColor Red
        }
        else {
            Write-Host "Triggering task '$TaskName' in the background..."
            Start-ScheduledTask -TaskName $TaskName
            Write-Host "SUCCESS: Task execution started. Check your logs/ directory for progress." -ForegroundColor Green
        }
    }
}
