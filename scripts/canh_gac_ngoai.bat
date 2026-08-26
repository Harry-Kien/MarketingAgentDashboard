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

cd /d "%~dp0.."
".venv\Scripts\python.exe" -m scripts.canh_gac_ngoai
exit /b %ERRORLEVEL%
