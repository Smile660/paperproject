@echo off
chcp 65001 >nul
setlocal
set "DB=C:\Users\14272\.zcode\cli\db\db.sqlite"
set "SQLITE=sqlite3"
where sqlite3 >nul 2>nul || set "SQLITE=D:\anaconda\Library\bin\sqlite3.exe"

if not exist "%DB%" (
  echo [错误] 找不到会话数据库: %DB%
  pause & exit /b 1
)

echo 正在迁移会话 sess_ed307cc8-3f4c-4863-b15b-98d8d87d9dba 到 paperproject 项目...
"%SQLITE%" "%DB%" "UPDATE session SET project_id='proj_d-project-paperproject', directory='D:\project\paperproject', path='D:\project\paperproject' WHERE id='sess_ed307cc8-3f4c-4863-b15b-98d8d87d9dba'; UPDATE input_history SET project_id='proj_d-project-paperproject' WHERE project_id='proj_c-users-14272-zcodeproject';"

echo.
echo === 验证（应显示 proj_d-project-paperproject ^| D:\project\paperproject）===
"%SQLITE%" "%DB%" "SELECT title||' @ '||project_id||' | '||directory FROM session;"
echo.
echo 完成。现在可以重新打开 ZCode 并选择 D:\project\paperproject 工作区。
pause
