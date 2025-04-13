; AutoHotkey script - يضغط حرف H كل 10 ثواني
toggle := false  ; حالة التشغيل

F8::  ; زر تشغيل / إيقاف
toggle := !toggle
if (toggle) {
    SetTimer, PressH, 10000
    ToolTip, ✅ بدأ الضغط كل 10 ثواني
} else {
    SetTimer, PressH, Off
    ToolTip, ⛔️ توقف الضغط
}
return

PressH:
SendInput, h
return
