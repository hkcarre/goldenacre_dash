# Launches goldenacre_insights_app.py - same SSLKEYLOGFILE workaround as
# run_vithit_app.ps1 (streamlit.exe's own startup crashes on the machine's
# persistent SSLKEYLOGFILE value before the app's own code ever runs).
#
# Usage: right-click > Run with PowerShell, or from a terminal: .\run_goldenacre_app.ps1

$env:SSLKEYLOGFILE = ""
Set-Location $PSScriptRoot
streamlit run goldenacre_insights_app.py
