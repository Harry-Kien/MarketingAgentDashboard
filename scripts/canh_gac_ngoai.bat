@echo off
REM Nguoi canh BEN NGOAI - chay bang Windows Task Scheduler moi 5 phut.
REM
REM CHU Y: file .bat KHONG duoc chua tieng Viet co dau. Windows doc no theo
REM bang ma he thong, khong phai UTF-8, nen dau tieng Viet lam vo ca file va
REM task chay sai lenh ma van bao thanh cong - dung loai hong ma nguoi canh
REM sinh ra de bat. Giai thich day du nam trong scripts/canh_gac_ngoai.py
REM
REM VI SAO CAN FILE NAY thay vi goi thang python: duong dan du an co dau
REM cach, va schtasks cat tham so /tr theo dau cach bat ke boc nhay the nao.
REM Mot file .bat thi Task Scheduler chi can biet mot duong dan duy nhat.
REM
REM Dang ky (chay mot lan):
REM   schtasks /create /tn "CanhGacMarketingAgent" /sc minute /mo 5
REM     /tr "D:\Marketing Dasbhboard CSKH\scripts\canh_gac_ngoai.bat" /st 00:00 /f
REM
REM Go:  schtasks /delete /tn "CanhGacMarketingAgent" /f

REM NHAT KY: Task Scheduler nuot stdout, nen truoc day khong co cach nao biet
REM nguoi canh da lam gi - 14.09.2026 khong tra duoc no co dung lai app sau
REM khi may bat lai hay khong. Ghi ra data\canh_gac_ngoai.log, moi lan mot
REM dong moc gio; qua 1 MB thi doi ten thanh .1 de khong phinh vo han.

cd /d "%~dp0.."
if not exist "data" mkdir "data"
for %%A in ("data\canh_gac_ngoai.log") do if exist "%%~A" if %%~zA GTR 1048576 move /y "data\canh_gac_ngoai.log" "data\canh_gac_ngoai.log.1" >nul
echo [%DATE% %TIME%] >> "data\canh_gac_ngoai.log"
".venv\Scripts\python.exe" -m scripts.canh_gac_ngoai >> "data\canh_gac_ngoai.log" 2>&1
exit /b %ERRORLEVEL%
