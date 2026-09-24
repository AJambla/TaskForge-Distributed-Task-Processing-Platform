# Stop ALL TaskForge bare-metal worker/scheduler/vite processes (leaves uvicorn API untouched).
$procs = Get-CimInstance Win32_Process | Where-Object {
  $cl = $_.CommandLine
  $cl -and (
    ($cl -match 'app\.worker\.main') -or
    ($cl -match 'app\.scheduler\.main') -or
    ($cl -match 'TaskForge.*vite')
  )
}
foreach ($p in $procs) {
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Output ("stopped {0}" -f $p.ProcessId)
  } catch {
    Write-Output ("FAILED  {0} : {1}" -f $p.ProcessId, $_.Exception.Message)
  }
}
