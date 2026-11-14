Unicode true
Name "Slur Tracker"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Slur Tracker"
InstallDirRegKey HKCU "Software\SlurTracker" "InstallDir"
RequestExecutionLevel user
Icon "${ICONFILE}"
UninstallIcon "${ICONFILE}"
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Slur Tracker"
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Slur Tracker"
  CreateShortcut "$SMPROGRAMS\Slur Tracker\Slur Tracker.lnk" "$INSTDIR\runtime\pythonw.exe" '"$INSTDIR\companion.py"' "$INSTDIR\st.ico"
  CreateShortcut "$SMPROGRAMS\Slur Tracker\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\SlurTracker" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "DisplayName" "Slur Tracker"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "DisplayIcon" "$INSTDIR\st.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker" "NoRepair" 1
SectionEnd

Function .onInstSuccess
  IfSilent done
  Exec '"$INSTDIR\runtime\pythonw.exe" "$INSTDIR\companion.py"'
  done:
FunctionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\Slur Tracker\Slur Tracker.lnk"
  Delete "$SMPROGRAMS\Slur Tracker\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Slur Tracker"
  DeleteRegKey HKCU "Software\SlurTracker"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SlurTracker"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\SlurTracker"
  Delete "$INSTDIR\companion.py"
  Delete "$INSTDIR\sync.py"
  Delete "$INSTDIR\cert.pem"
  Delete "$INSTDIR\st.ico"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\qt-notice.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
