; _internal contains only generated backend dependencies. Never remove siblings
; (ai-memory, licenses), the installation root, or application/user data.
!include "LogicLib.nsh"
!include "Win\RestartManager.nsh"

; PREINSTALL precedes Tauri's own running-app check. Query both executables
; without shutting down owners, and close the session before any file deletion.
Function AxxRequireBackendIdle
  Exch $6 ; Main executable path: Tauri defines its name after including hooks.
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  StrCpy $5 0
  !insertmacro RestartManager_StartSession $4
  StrCmp $4 "" axx_backend_idle_failed
  !insertmacro RestartManager_RegisterFile $4 "$6"
  IntCmp $0 0 0 axx_backend_idle_query_failed axx_backend_idle_query_failed
  !insertmacro RestartManager_RegisterFile $4 "$INSTDIR\resources\axx-backend.exe"
  IntCmp $0 0 0 axx_backend_idle_query_failed axx_backend_idle_query_failed
  StrCpy $1 0
  StrCpy $2 0
  StrCpy $3 0
  System::Call 'RSTRTMGR::RmGetList(i r4, *i .r1, *i .r2, p0, *i .r3) i.r0'
  ; ERROR_MORE_DATA means there are owners. Every other error also fails closed.
  IntCmp $0 0 0 axx_backend_idle_query_failed axx_backend_idle_query_failed
  IntCmp $1 0 0 axx_backend_idle_query_failed axx_backend_idle_query_failed
  IntCmp $2 0 axx_backend_idle_close_session axx_backend_idle_query_failed axx_backend_idle_query_failed
axx_backend_idle_query_failed:
  StrCpy $5 1
axx_backend_idle_close_session:
  System::Call 'RSTRTMGR::RmEndSession(i r4) i.r3'
  IntCmp $3 0 0 axx_backend_idle_failed axx_backend_idle_failed
  IntCmp $5 0 axx_backend_idle_ok axx_backend_idle_failed axx_backend_idle_failed
axx_backend_idle_failed:
  SetErrorLevel 2
  Abort "Cannot replace backend dependencies while Axx or its backend is running, or their idle state cannot be verified. Close them and retry; no dependency files were deleted."
axx_backend_idle_ok:
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  Pop $6
FunctionEnd

Function AxxRemoveBackendDirectory
  Exch $0
  Push $1
  Push $2
  Push $3
  Push $4

  System::Call 'kernel32::GetFileAttributesW(w r0) i.r3'
  ${If} $3 = -1
    Goto axx_backend_cleanup_failed
  ${EndIf}
  IntOp $4 $3 & 0x400 ; FILE_ATTRIBUTE_REPARSE_POINT
  ${If} $4 != 0
    Goto axx_backend_cleanup_failed
  ${EndIf}
  IntOp $4 $3 & 0x10 ; FILE_ATTRIBUTE_DIRECTORY
  ${If} $4 = 0
    Goto axx_backend_cleanup_failed
  ${EndIf}

  ClearErrors
  FindFirst $1 $2 "$0\*"
  IfErrors axx_backend_remove_directory
axx_backend_next_entry:
  ${If} $2 != "."
  ${AndIf} $2 != ".."
    System::Call 'kernel32::GetFileAttributesW(w "$0\$2") i.r3'
    ${If} $3 = -1
      Goto axx_backend_cleanup_failed
    ${EndIf}
    IntOp $4 $3 & 0x400
    ${If} $4 != 0
      Goto axx_backend_cleanup_failed
    ${EndIf}
    IntOp $4 $3 & 0x10
    ${If} $4 != 0
      Push "$0\$2"
      Call AxxRemoveBackendDirectory
    ${Else}
      ClearErrors
      Delete "$0\$2"
      IfErrors axx_backend_cleanup_failed
    ${EndIf}
  ${EndIf}
  FindNext $1 $2
  IfErrors 0 axx_backend_next_entry
  FindClose $1
axx_backend_remove_directory:
  ClearErrors
  RMDir "$0"
  IfErrors axx_backend_cleanup_failed
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  Return

axx_backend_cleanup_failed:
  SetErrorLevel 2
  Abort "Cannot safely replace backend dependencies in $0. Close Axx and its backend, check file permissions, then retry."
FunctionEnd

!macro NSIS_HOOK_PREINSTALL
  Push $R7
  Push $R8
  Push $R9
  GetFullPathName $R8 "$INSTDIR"
  GetFullPathName $R9 "$INSTDIR\resources\_internal"
  IfFileExists "$R9" 0 axx_backend_cleanup_done
  ; An existing application is required before deleting an existing bundle.
  IfFileExists "$R8\${MAINBINARYNAME}.exe" 0 axx_backend_cleanup_refused
  System::Call 'kernel32::GetFileAttributesW(w "$R8\${MAINBINARYNAME}.exe") i.R7'
  IntOp $R7 $R7 & 0x410 ; The marker must be a regular file, not a directory/link.
  IntCmp $R7 0 0 axx_backend_cleanup_refused axx_backend_cleanup_refused
  GetFullPathName $R7 "$R9\..\.."
  StrCmp $R7 $R8 0 axx_backend_cleanup_refused
  System::Call 'kernel32::GetFileAttributesW(w R8) i.R7'
  IntOp $R7 $R7 & 0x400
  IntCmp $R7 0 0 axx_backend_cleanup_refused axx_backend_cleanup_refused
  System::Call 'kernel32::GetFileAttributesW(w "$R8\resources") i.R7'
  IntOp $R7 $R7 & 0x400
  IntCmp $R7 0 0 axx_backend_cleanup_refused axx_backend_cleanup_refused

  Push "$R8\${MAINBINARYNAME}.exe"
  Call AxxRequireBackendIdle
  ; Remaining locked files fail below; never schedule deletion on reboot.
  Push $R9
  Call AxxRemoveBackendDirectory
  Goto axx_backend_cleanup_done

axx_backend_cleanup_refused:
  SetErrorLevel 2
  Abort "Refusing backend cleanup: the existing Axx installation is missing or its resource directory is a link."
axx_backend_cleanup_done:
  Pop $R9
  Pop $R8
  Pop $R7
!macroend
