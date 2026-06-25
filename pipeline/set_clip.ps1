Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile('C:\Users\nL_ku\ngernduangold-site\automation-log\ig-cards\card-profile.png')
[System.Windows.Forms.Clipboard]::SetImage($img)
Write-Output 'clipboard-image-set'
