$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$lineas = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'alerta_texto.txt') -Encoding UTF8
$banner = $lineas[0]
$color  = $lineas[1]
$url    = $lineas[2]
$url2   = $lineas[3]
$cuerpo = ($lineas | Select-Object -Skip 4) -join "`r`n"

$form = New-Object System.Windows.Forms.Form
$form.Text = 'PREVIFUEGO - Alerta SERCOP'
$form.Size = New-Object System.Drawing.Size(1000, 640)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::White

$tb = New-Object System.Windows.Forms.TextBox
$tb.Multiline = $true
$tb.ReadOnly = $true
$tb.Dock = 'Fill'
$tb.ScrollBars = 'Vertical'
$tb.BorderStyle = 'None'
$tb.BackColor = [System.Drawing.Color]::White
$tb.Font = New-Object System.Drawing.Font('Segoe UI', 13)
$tb.Text = $cuerpo
$tb.SelectionStart = 0
$tb.SelectionLength = 0

$panel = New-Object System.Windows.Forms.Panel
$panel.Dock = 'Bottom'
$panel.Height = 84

$btnWeb = New-Object System.Windows.Forms.Button
$btnWeb.Text = 'ABRIR PORTAL SERCOP'
$btnWeb.Size = New-Object System.Drawing.Size(320, 54)
$btnWeb.Location = New-Object System.Drawing.Point(20, 14)
$btnWeb.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$btnWeb.Add_Click({ Start-Process $url })

$btnOk = New-Object System.Windows.Forms.Button
$btnOk.Text = 'ENTENDIDO'
$btnOk.Size = New-Object System.Drawing.Size(240, 54)
$btnOk.Location = New-Object System.Drawing.Point(720, 14)
$btnOk.Anchor = 'Top,Right'
$btnOk.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$btnOk.Add_Click({ $form.Close() })

$panel.Controls.Add($btnWeb)
if ($url2 -and $url2.Trim() -ne '') {
    $btnRes = New-Object System.Windows.Forms.Button
    $btnRes.Text = 'ABRIR RESUMEN'
    $btnRes.Size = New-Object System.Drawing.Size(260, 54)
    $btnRes.Location = New-Object System.Drawing.Point(360, 14)
    $btnRes.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
    $btnRes.Add_Click({ Start-Process $url2 })
    $panel.Controls.Add($btnRes)
}
$panel.Controls.Add($btnOk)

$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = $banner
$lbl.Dock = 'Top'
$lbl.Height = 110
$lbl.TextAlign = 'MiddleCenter'
$lbl.ForeColor = [System.Drawing.Color]::White
$lbl.BackColor = [System.Drawing.Color]::FromName($color)
$lbl.Font = New-Object System.Drawing.Font('Segoe UI', 22, [System.Drawing.FontStyle]::Bold)

$form.Controls.Add($tb)
$form.Controls.Add($panel)
$form.Controls.Add($lbl)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 30000
$timer.Add_Tick({ [System.Media.SystemSounds]::Exclamation.Play() })
$form.Add_Shown({
    $form.Activate()
    [System.Media.SystemSounds]::Exclamation.Play()
    $timer.Start()
})
$form.Add_FormClosed({ $timer.Stop() })

[void]$form.ShowDialog()
