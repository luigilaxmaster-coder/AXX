; _internal contains only generated backend dependencies. Never remove siblings
; (ai-memory, licenses), the installation root, or application/user data.
!include "LogicLib.nsh"

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

  ; The delivery flow closes Axx before invoking NSIS. Locked files fail below;
  ; this hook never kills a process or schedules deferred deletion on reboot.
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
