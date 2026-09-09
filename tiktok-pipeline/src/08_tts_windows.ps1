param(
    [Parameter(Mandatory = $true)]
    [string]$TextFile,

    [Parameter(Mandatory = $true)]
    [string]$OutFile,

    [string]$VoiceLanguage = "th-TH",
    [double]$SpeakingRate = 0.95
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSEdition -ne "Desktop") {
    throw "Run this script with Windows PowerShell 5.1 (powershell.exe), not PowerShell 7."
}
if (-not (Test-Path -LiteralPath $TextFile -PathType Leaf)) {
    throw "Text file not found: $TextFile"
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

function Await-WinRt {
    param($Operation, [Type]$ResultType)

    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -like "IAsyncOperation*"
        } |
        Select-Object -First 1
    if ($null -eq $method) {
        throw "Windows Runtime AsTask adapter is unavailable."
    }
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$text = (Get-Content -LiteralPath $TextFile -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($text)) {
    throw "Text file is empty: $TextFile"
}

$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
    Where-Object { $_.Language -eq $VoiceLanguage } |
    Select-Object -First 1
if ($null -eq $voice) {
    throw "No installed voice for language $VoiceLanguage"
}

$target = [System.IO.Path]::GetFullPath($OutFile)
$parent = [System.IO.Path]::GetDirectoryName($target)
if (-not [string]::IsNullOrWhiteSpace($parent)) {
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
}

$synth = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::New()
$reader = $null
try {
    $synth.Voice = $voice
    $synth.Options.SpeakingRate = $SpeakingRate
    $stream = Await-WinRt ($synth.SynthesizeTextToStreamAsync($text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    if ($stream.Size -le 44) {
        throw "Speech synthesis returned an empty stream."
    }
    $reader = [Windows.Storage.Streams.DataReader]::New($stream)
    $loaded = Await-WinRt ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
    $bytes = New-Object byte[] $loaded
    $reader.ReadBytes($bytes)
    [System.IO.File]::WriteAllBytes($target, $bytes)
}
finally {
    if ($null -ne $reader) { $reader.Dispose() }
    $synth.Dispose()
}

$file = Get-Item -LiteralPath $target
if ($file.Length -le 44) {
    throw "Speech file was not produced correctly: $target"
}
Write-Output ("[08_tts_windows] {0} ({1}, {2} bytes)" -f $target, $voice.DisplayName, $file.Length)
