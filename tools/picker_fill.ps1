param([Parameter(Mandatory=$true)][string]$FilePath)
$code = @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class DlgFill3 {
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lp);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc cb, IntPtr lp);
  [DllImport("user32.dll")] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] static extern IntPtr GetDlgItem(IntPtr h, int id);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr wp, string lp);
  [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  delegate bool EnumWindowsProc(IntPtr h, IntPtr lp);
  const uint WM_SETTEXT = 0x000C;
  const uint BM_CLICK = 0x00F5;
  public static IntPtr Dialog = IntPtr.Zero;
  public static string Log = "";
  public static void Scan() {
    Dialog = IntPtr.Zero;
    EnumWindows((h, lp) => {
      if (!IsWindowVisible(h)) return true;
      var cls = new StringBuilder(256); GetClassName(h, cls, 256);
      if (cls.ToString() != "#32770") return true;
      Dialog = h;
      return false;
    }, IntPtr.Zero);
  }
  public static bool Fill(string path) {
    if (Dialog == IntPtr.Zero) return false;
    var edits = new List<IntPtr>();
    EnumChildWindows(Dialog, (h, lp) => {
      var cls = new StringBuilder(256); GetClassName(h, cls, 256);
      if (cls.ToString() == "Edit") edits.Add(h);
      return true;
    }, IntPtr.Zero);
    Log += "EDITS=" + edits.Count + ";";
    if (edits.Count == 0) { Log += "NO_EDIT;"; return false; }
    SendMessage(edits[0], WM_SETTEXT, IntPtr.Zero, path);
    Log += "SETTEXT_OK;";
    IntPtr ok = GetDlgItem(Dialog, 1); // IDOK = Open button
    if (ok == IntPtr.Zero) { Log += "NO_IDOK;"; return false; }
    SetForegroundWindow(Dialog);
    System.Threading.Thread.Sleep(400);
    SendMessage(ok, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
    Log += "IDOK_CLICKED;";
    return true;
  }
}
'@
Add-Type -TypeDefinition $code
$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
  [DlgFill3]::Scan()
  if ([DlgFill3]::Dialog -ne [IntPtr]::Zero) { break }
  Start-Sleep -Milliseconds 500
}
if ([DlgFill3]::Dialog -eq [IntPtr]::Zero) { Write-Output 'NO_DIALOG_FOUND'; exit 1 }
$ok = [DlgFill3]::Fill($FilePath)
Write-Output ('LOG: ' + [DlgFill3]::Log)
Start-Sleep -Milliseconds 1500
[DlgFill3]::Scan()
if ([DlgFill3]::Dialog -eq [IntPtr]::Zero) { Write-Output 'DIALOG_CLOSED_OK' } else { Write-Output 'DIALOG_STILL_OPEN' }
